import enum
import math
import time
import sys
import os
import cmath
import yaml
import logging
import multiprocessing
import pyodbc
import pandas as pd
import numpy as np
import py_dss_interface
#from py_dss_toolkit import dss_tools
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
from collections import Counter
from dataclasses import dataclass, asdict
from create_result_db import insert_data, check_cenario_exist, nome_tabelas

from sqlalchemy.sql.coercions import expect

logging.basicConfig(filename='CTRL_SmartRT_new.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d,%H:%M:%S')


def gerador_positivo_negativo():
    numero = 1
    while True:
        yield numero
        yield -numero
        numero += 1


class Feeder_Condition:
    def __init__(self, utility, substation, feeder, dss_file, num_patamares, patamar_ini, patamar_fim, cenario, controle):
        dss = py_dss_interface.DSS()
        #dss_tools.update_dss(dss)
        self.dss = dss
        #self.dss_tools = dss_tools

        self.utility = utility
        self.substation = substation
        self.feeder = feeder
        self.dss_file = dss_file
        self.total_patamar = num_patamares
        self.patamar_ini = patamar_ini
        self.patamar_fim = patamar_fim
        self.cenario_id = cenario.split(",")[0]
        self.cenario = cenario.split(",")[1]
        self.controle_id = controle.split(",")[0]
        self.controle = controle.split(",")[1]

        print(f"🚀 Processando o Alimentador:{self.feeder}; Cenário:{self.cenario}; Controle:{self.controle} | {multiprocessing.current_process().name}")

        # ensure DSS is ready
        self._read_dss_file()

        # Verifica a correta atribuição das tensões de base para todas as barras
        self.__check_kv_base()

        # add monitor at first element
        self.monitor = self.__add_monitor_powers()

        # Entradas para os capacitores
        self.num_steps = 14
        self.capacitor_name = ''

        # Verifica o cenário e as modificações do DSS necessárias
        self.enable_VoltageControl = False
        self.on_VoltageControl = 0.94
        self.off_VoltageControl = 1.04

        self.enable_TimeControl = False
        self.on_TimeControl = 7
        self.off_TimeControl = 23

        self.__edit_capacitor(self.enable_VoltageControl, self.enable_TimeControl, self.capacitor_name)

        # Acrescenta monitores nos capacitores
        self.__add_monitor_cap()

        # verifica se já existe o cenario no banco de dados e apaga os dados para serem substituidos
        check_cenario_exist(nome_tabelas(), self.feeder, self.cenario_id, self.controle_id)

        # salva os dados de configuração do cenario
        self.__save_cenario()

    def __edit_capacitor(self, enable_VoltageControl, enable_TimeControl, capacitor_name):
        """ Implementa modificações no OpenDSS para a criação do cenario"""
        self.dss.text(f"batchedit capacitor..* conn=wye")  # TODO parece que o comando não funciona
        self.dss.text("edit Capacitor.c1 conn=wye")

        if self.controle == 'Tensao' and enable_VoltageControl == False:
                kvar = self.dss.capacitors.kvar
                n_steps = int(kvar/150)                 #Todo Minimo valor de kvar existente na base de dados
                self.dss.capacitors.num_steps = n_steps
                self.dss.capacitors.states = [0] * n_steps      # iniciar com todos os passos desligados

        elif self.controle == 'Tensao' and enable_VoltageControl == True:
                self.dss.capcontrols.on_setting = (kv_cap / pt_ratio) * 0.95   # 218.5 -> 0.95 pu
            self.dss.text(f'edit CapControl.C1ctrl_{capacitor_name.split('_')[1]} enable = False')
            print(f'Controle {self.controle}: Capacitor alterado para VoltageControl')

        # if self.controle == 'Tensao':
        #     for ctrl_cap in self.dss.capcontrols.names:
        #         self.dss.capcontrols.name = ctrl_cap        # ativa o controle do capacitor
        #         self.dss.capcontrols.mode = 1               # Voltage
        #         pt_ratio = self.dss.capcontrols.pt_ratio
        #
        #         self.dss.capacitors.name = self.dss.capcontrols.controlled_capacitor
        #         self.dss.capacitors.num_steps = 14
        #         self.dss.capacitors.states = [0] * 14      # iniciar com todos os passos desligados
        #         kv_cap = (self.dss.capacitors.kv * 1000) #/ np.sqrt(3)
        #         self.dss.text(f"enable capacitor.{self.dss.capacitors.name}")
        #
        #         self.dss.capcontrols.name = ctrl_cap  # ativa o controle do capacitor
        #         self.dss.capcontrols.on_setting = (kv_cap / pt_ratio) * 1.1   # 218.5 -> 0.95 pu
        #         self.dss.capcontrols.off_setting = (kv_cap / pt_ratio) * 1.3     # 230   -> 1 pu
        #         #self.dss.text(f"enable CapControl.{ctrl_cap}")
        #         self.dss.text(f"edit capcontrol.{ctrl_cap} enabled=true")
        #
        #         print(f'{self.dss.capcontrols.name}; {self.dss.capcontrols.mode}; {self.dss.capacitors.num_steps},'
        #               f'{self.dss.capacitors.states}, {self.dss.capcontrols.on_setting}, {self.dss.capcontrols.off_setting}')
        #     print(f'Capacitores alterados para VoltageControl!')

        elif self.controle == 'kvar':
            for ctrl_cap in self.dss.capcontrols.names:
                self.dss.capcontrols.name = ctrl_cap  # ativa o controle do capacitor
                self.dss.text(f"edit capcontrol.{ctrl_cap} enabled=true")
                self.dss.capcontrols.mode = 2         # KVARCONTROL

                self.dss.capacitors.name = self.dss.capcontrols.controlled_capacitor
                kvar = self.dss.capacitors.kvar
                n_steps = int(kvar/150)
                self.dss.capacitors.num_steps = n_steps
                self.dss.capacitors.states = [0] * n_steps  # iniciar com todos os passos desligados
                self.dss.text(f"enable capacitor.{self.dss.capacitors.name}")

                self.dss.capcontrols.name = ctrl_cap  # ativa o controle do capacitor
                self.dss.capcontrols.on_setting = kvar / 4  # 300
                self.dss.capcontrols.off_setting = kvar / 12  # 100
                self.dss.text(f"edit capcontrol.{self.dss.capcontrols.name} enabled=true")

                print(f'{self.dss.capcontrols.name}; modo:{self.dss.capcontrols.mode}; num_step:{self.dss.capacitors.num_steps},'
                      f'{self.dss.capacitors.states}, {self.dss.capcontrols.on_setting}, {self.dss.capcontrols.off_setting}')
            print(f'Capacitores alterados para KVARControl!')

        elif self.controle == 'Tempo' and enable_TimeControl == False:
            for cap_name in self.dss.capacitors.names:
                self.dss.text(f"disable Capacitor.{cap_name}")
                self.dss.text(f'edit CapControl.C1ctrl_{cap_name.split('_')[1]} enable = False')
                self.dss.capcontrols.on_setting = 8.0

        elif self.controle == 'Tempo' and enable_TimeControl == True:
                kvar = self.dss.capacitors.kvar
                n_steps = int(kvar/150)
                self.dss.capacitors.num_steps = n_steps
                self.dss.capacitors.states = [0] * n_steps  # iniciar com todos os passos desligados

        # elif self.controle == 'Tempo':
        #     for ctrl_cap in self.dss.capcontrols.names:
        #         self.dss.capcontrols.name = ctrl_cap   # ativa o controle do capacitor
        #         self.dss.capcontrols.mode = 3          # Time
        #         self.dss.capcontrols.on_setting = 7.0
        #         self.dss.capcontrols.off_setting = 23.0
        #         #self.dss.text(f"enable CapControl.{ctrl_cap}")
        #         self.dss.text(f"edit capcontrol.{ctrl_cap} enabled=true")
        #
        #         self.dss.capacitors.name = self.dss.capcontrols.controlled_capacitor
        #         self.dss.capacitors.num_steps = 14
        #         self.dss.capacitors.states = [0] * 14  # iniciar com todos os passos desligados
        #         self.dss.text(f"enable capacitor.{self.dss.capacitors.name}")
        #
        #         print(f'{self.dss.capcontrols.name}; Modo:{self.dss.capcontrols.mode}; num_step:{self.dss.capacitors.num_steps}; '
        #               f'States:{self.dss.capacitors.states}; on_setting:{self.dss.capcontrols.on_setting}; off_setting:{self.dss.capcontrols.off_setting}')
        #     print(f'Controle {self.controle}: Capacitores alterados para TimeControl')

        elif self.controle == 'FP':
            for ctrl_cap in self.dss.capcontrols.names:
                self.dss.capcontrols.name = ctrl_cap   # ativa o controle do capacitor
                self.dss.capcontrols.mode = 4          # PF
                self.dss.capcontrols.on_setting = 0.90
                self.dss.capcontrols.off_setting = 0.95
                #self.dss.text(f"enable CapControl.{ctrl_cap}")
                self.dss.text(f"edit capcontrol.{ctrl_cap} enabled=true")


                self.dss.capacitors.name = self.dss.capcontrols.controlled_capacitor
                kvar = self.dss.capacitors.kvar
                n_steps = int(kvar/150)
                self.dss.capacitors.num_steps = n_steps
                self.dss.capacitors.states = [0] * n_steps  # iniciar com todos os passos desligados
                self.dss.text(f"enable capacitor.{self.dss.capacitors.name}")

                print(f'{self.dss.capcontrols.name}; modo:{self.dss.capcontrols.mode}; num_step:{self.dss.capacitors.num_steps},'
                      f'{self.dss.capacitors.states}')
            print(f'Capacitores alterados para PFControl!')

        elif self.controle == 'Fixo':
            for capctrl_name in self.dss.capcontrols.names:
                self.dss.text(f'edit CapControl.{capctrl_name} enable = False')
            print(f'Controle {self.controle}: Capacitores sempre ligados')

        elif self.controle == 'Desligado':
            for cap_name in self.dss.capacitors.names:
                self.dss.text(f"disable Capacitor.{cap_name}")
                self.dss.text(f'edit CapControl.C1ctrl_{cap_name.split('_')[1]} enable = False')
            print(f'Capacitor {self.controle}')

        else:
            print(f'Cenário ou Controle não definidos: {self.cenario} - {self.controle}')

    def __add_monitor_cap(self):
        for cap_name in self.dss.capacitors.names:
            self.dss.text(f"new monitor.{cap_name}_volt_curr element=Capacitor.{cap_name} terminal=1 mode=0 ppolar=no")

    def __add_monitor_powers(self):
        """ Navega pela topologia da rede de um bus qualquer até o início do circuito
            Adiciona o monitor de potência no início do circuito
        """
        self.dss.topology.first()
        self.dss.topology.forward_branch()
        while True:
            index_branch = self.dss.topology.backward_branch()
            if index_branch:  # chegou no inicio do alimentador (Vsource)
                self.dss.topology.forward_branch()  # avançar para obter o primeiro elemento
                # print(self.dss.topology.branch_name)
                first_elem = self.dss.topology.branch_name
                self.dss.text(f"new monitor.{first_elem}_powers element={first_elem} terminal=1 mode=1 ppolar=no")
                self.monitor = f'{first_elem}_powers'

                return self.monitor

    def _read_dss_file(self):
        """
        Leitura do arquivo 'master' sem executar o 'solve' e com os medidores desabilitados.
        """
        self.dss.dssinterface.clear_all()
        self.dss.text(f"set Datapath = '{os.path.dirname(self.dss_file)}'")
        with open(os.path.join(self.dss_file), 'r') as file:
            for line_dss in file:
                if not (line_dss.startswith('!') or line_dss.startswith('\n') or line_dss.lower().startswith('clear')):
                    self.dss.text(line_dss.strip('\n'))
                if 'calc' in line_dss:
                    break

        self.dss.text("set normvminpu = 0.93")
        self.dss.text("set mode = daily")
        self.dss.text("set controlmode = time")   # time  static
        self.dss.text("set tolerance = 0.0001")
        self.dss.text("set maxcontroliter = 100")
        self.dss.text("set maxiterations = 100")

        if self.total_patamar == 24:
            self.dss.text(f"set stepsize = 1h")
            horas = self.patamar_ini
            total_sec = 0

        else:
            self.dss.text(f"set stepsize = {86400 / self.total_patamar}s")
            segundos_totais = int(self.patamar_ini * 86400 / self.total_patamar)
            minutos, segundos = divmod(segundos_totais, 60)
            horas, minutos = divmod(minutos, 60)
            total_sec = minutos * 60 + segundos

        self.dss.text("set number = 1")
        self.dss.text(f"set time = ({horas}, {total_sec})")

        return

    def __check_kv_base(self):
        """
        Verifica a tensão de base definida pelo openDSS para as todas as barras conectadas
        no secundario dos transformadores.
        São obtidas as tensões de fase para a barra do secundario do TR e comparada com a informada pelo openDSS
        Em caso de diferença são localizadas todas barras conectadas no secundario do transformador e set o kv_base
        de todas as barras com o valor obtido da avaliação das conexões do transformador.
        :return:
        """
        tr_map = dict()
        n = 0
        vln = vll = None

        # Identifica grupo de transformadores monofásicos em delta aberto
        self.dss.transformers.first()
        for _ in range(self.dss.transformers.count):
            transformer_name = self.dss.transformers.name
            if transformer_name.lower().startswith("reg"):
                self.dss.transformers.next()
                continue

            self.dss.circuit.set_active_element(f"transformer.{self.dss.transformers.name}")
            if self.dss.cktelement.num_phases == 1:
                nome_barra_sec = self.dss.cktelement._bus_names()[1].split('.')[0].lower()
                tr_map[self.dss.transformers.name] = (nome_barra_sec)
            self.dss.transformers.next()

        nome_barra_trafo_delta = Counter(tr_map.values())

        self.dss.transformers.first()
        for _ in range(self.dss.transformers.count):
            transformer_name = self.dss.transformers.name
            if transformer_name.lower().startswith("reg"):
                self.dss.transformers.next()
                continue

            self.dss.circuit.set_active_element(f"transformer.{transformer_name}")
            bus_name_sec = self.dss.cktelement.bus_names[1].split('.')[0].lower()
            num_trafo_monofasicos = nome_barra_trafo_delta[bus_name_sec]
            tr_ph = self.dss.cktelement.num_phases

            if tr_ph == 3 or num_trafo_monofasicos == 3:
                self.dss.transformers.wdg = 2
                vll = self.dss.transformers.kv
                vln = self.dss.transformers.kv / np.sqrt(3)
            elif tr_ph == 1:
                num_wdg = self.dss.transformers.num_windings
                if num_wdg == 2:
                    self.dss.transformers.wdg = 2  # monofasico
                    if self.dss.transformers.is_delta:
                        vll = self.dss.transformers.kv
                        vln = self.dss.transformers.kv / 2
                    else:
                        vln = self.dss.transformers.kv
                        vll = self.dss.transformers.kv * 2
                elif num_wdg == 3:  # monofasico MRT
                    self.dss.transformers.wdg = 2
                    vln = self.dss.transformers.kv
                    vll = self.dss.transformers.kv * 2

            self.dss.circuit.set_active_bus(self.dss.cktelement.bus_names[1])
            bus_transformer_name = self.dss.bus.name
            kv_base = self.dss.bus.kv_base

            # Verifica se há diferença entre o calculado e o descrito pelo OpenDSS
            if round(vln, 3) != round(kv_base, 3):
                if n == 0:
                    n += 1
                    print(f'CHECK KV BASE - {self.feeder}')

                self.dss.text(f'SetkVBase Bus={bus_transformer_name} kVLN={vln}')
                # print(f"Transformer:{transformer_name} Bus:{bus_transformer_name} kv_base:{kv_base} - new_kv_base:{vln}")

                # Localizar o transformador que teve o valor de kvbase alterado por meio da topologia
                self.dss.topology.first()
                while True:
                    indx = self.dss.topology.active_branch
                    indx_level = self.dss.topology.active_level
                    branch_name = self.dss.topology.branch_name
                    if branch_name == f"Transformer.{transformer_name}":
                        self.dss.circuit.set_active_element(f"transformer.{transformer_name}")
                        self.dss.circuit.set_active_bus(bus_transformer_name)
                        # encontrou o transformador que foi alterado com setkvbase
                        break
                    index_branch = self.dss.topology.forward_branch()

                # busca os ramais conectados neste transformador
                while True:
                    index_branch_2 = self.dss.topology.next()
                    indx_level_2 = self.dss.topology.active_level
                    branch_name_2 = self.dss.topology.branch_name
                    if not self.dss.topology.branch_name.startswith(('Line.sbt', 'Line.rbt')):
                        # print('\n Proximo transformador !!! \n')
                        break
                    self.dss.circuit.set_active_element(branch_name_2)
                    self.dss.circuit.set_active_bus(self.dss.cktelement.bus_names[1])
                    bus_line_name = self.dss.bus.name
                    kv_base_2 = self.dss.bus.kv_base
                    # print(f'{branch_name_2}: {dss.cktelement.bus_names}: {kv_base_2}')
                    self.dss.text(f'SetkVBase Bus={bus_line_name} kVLN={vln}')
                    # print(f'Valor alterado: {self.dss.cktelement.bus_names[1]} - kvbase:{self.dss.bus.kv_base}')

            self.dss.transformers.next()

    def __csv2db(self, path_csv, number, hour, sec):
        tabela = 'linha'
        dados = pd.read_csv(path_csv)
        dados = dados[['Name', ' Distance1',' puV1',' Distance2',' puV2',' Color',' Linetype']]
        dados.columns = ['linha', 'distancia1', 'v1', 'distancia2', 'v2', 'node', 'tipo']
        dados['cenario_id'] = self.cenario_id
        dados['circuito'] = self.feeder
        dados['controle_id'] = self.controle_id
        dados['patamar'] = number
        dados['hora'] = hour
        dados['seg'] = sec
        dados = dados.to_dict('records')
        try:
            insert_data(tabela, dados)
        except:
            print(f'Error: linha -  insert database...{path_csv}')

    def __save_results_db(self, tabela, dados):
        try:
            insert_data(tabela, dados)
        except:
            print('Error: insert database...')

    def __save_cenario(self):
        data = {'cenario_id': self.cenario_id, 'cenario': self.cenario, 'empresa': self.utility, 'sub': self.substation,
                'circuito': self.feeder, 'controle_id': self.controle_id, 'controle': self.controle,
                'patamar_ini': self.patamar_ini, 'patamar_fim': self.patamar_fim, 'data': datetime.today().strftime('%Y%m%d')}
        try:
            insert_data('analise', [data])
        except:
            print('Error: insert database...')

    def _read_voltage_cap(self):
        for capacitor_name in self.dss.capacitors.names:
            self.dss.monitors.name = capacitor_name
            print(f'Capacitor: {capacitor_name} '
                  f'kV: {self.dss.monitors.channel(1)[-1]/7967}  {self.dss.monitors.channel(3)[-1]/7967} {self.dss.monitors.channel(5)[-1]/7967}')

    def _read_cap(self, number, hour, sec, data_cap):
        cap_rows = []
        cap_dados_rows = []

        for capacitor_name in self.dss.capacitors.names:
            vmag = []
            kvar = kv_base = current_steps = available_steps = 0
            pt_ratio = ct_ratio = ctrl_on = ctrl_off = 0
            delay = delay_off = dead_time = 0
            ctrl_mode = 999

            self.dss.capacitors.name = capacitor_name
            self.dss.circuit.set_active_element(f"capacitor.{self.dss.capacitors.name}")
            kvar = self.dss.capacitors.kvar
            current_steps = sum(self.dss.capacitors.states)
            available_steps = self.dss.capacitors.available_steps

            capacitor_bus = self.dss.cktelement.bus_names
            #Todo incluir distancia do capacitor à subestação para definir diferentes delays entre os calacitores ao longo do circcuito
            self.dss.circuit.set_active_bus(capacitor_bus[0])
            kv_base = self.dss.bus.kv_base
            for node in range(self.dss.bus.num_nodes):
                try:
                    vmag.append(self.dss.bus.vmag_angle_pu[node * 2])
                except IndexError:
                    print('')

            for ctrl_cap in self.dss.capcontrols.names:
                if self.controle == "Desligado":
                    current_steps = 0
                    continue

                self.dss.capcontrols.name = ctrl_cap
                capacitor_ctrl = self.dss.capcontrols.controlled_capacitor

                if capacitor_ctrl == capacitor_name:
                    if self.dss.cktelement.is_enabled == 0:
                        current_steps = 0

                    delay = self.dss.capcontrols.delay
                    delay_off = self.dss.capcontrols.delay_off
                    dead_time = self.dss.capcontrols.dead_time

                    if self.controle == 'Tensao':
                        ctrl_mode = 1

                    if self.controle == 'Tempo':
                        ctrl_mode = 3

                    if ctrl_mode == 0: # Corrente
                        ct_ratio = self.dss.capcontrols.ct_ratio
                        ctrl_on = self.dss.capcontrols.on_setting
                        ctrl_off = self.dss.capcontrols.off_setting

                    elif ctrl_mode == 1: # Tensão
                        ctrl_on = self.on_VoltageControl
                        ctrl_off = self.off_VoltageControl
                        if data_cap[capacitor_name]["Step"] == 0:
                            current_steps = data_cap[capacitor_name]["Step"]
                        current_steps = data_cap[capacitor_name]["Step"] - 1

                    elif ctrl_mode == 2: # kvar
                        ct_ratio = self.dss.capcontrols.ct_ratio
                        ctrl_on = self.dss.capcontrols.on_setting
                        ctrl_off = self.dss.capcontrols.off_setting

                    elif ctrl_mode == 3: # Tempo
                        ctrl_on = self.on_TimeControl
                        ctrl_off = self.off_TimeControl
                        if ctrl_on <= hour <= ctrl_off:
                            current_steps = 1

                    elif ctrl_mode == 4: # PF
                        ctrl_on = self.dss.capcontrols.on_setting
                        ctrl_off = self.dss.capcontrols.off_setting

                    else: # Fixo
                        current_steps = 1

            cap_dados_rows.append({"cenario_id": self.cenario_id,
                                   "circuito": self.feeder,
                                   "controle_id": self.controle_id,
                                   "nome": capacitor_name,
                                   "patamar": number,
                                   "hora": hour,
                                   "seg": sec,
                                   "step": current_steps,
                                   "vmag_1": vmag[0],
                                   "vmag_2": vmag[1],
                                   "vmag_3": vmag[2],
                                   "available_steps": available_steps
                                   })

            cap_rows.append({"cenario_id": self.cenario_id,
                             "circuito": self.feeder,
                             "nome": capacitor_name,
                             "controle": self.controle,
                             "controle_id": self.controle_id,
                             "kvar": kvar,
                             "pt_ratio": pt_ratio,
                             "ct_ratio": ct_ratio,
                             "ctrl_on": ctrl_on,
                             "ctrl_off": ctrl_off,
                             "delay": delay,
                             "delay_off": delay_off,
                             "dead_time": dead_time,
                             "kv_base": kv_base
                             })
            print(f"{capacitor_name}; step:{current_steps}; ctrl_on:{ctrl_on}; ctrl_off:{ctrl_off}")

        if number == 0:
            self.__save_results_db("equipamento", cap_rows)

        self.__save_results_db("capacitor", cap_dados_rows)

    def _read_powers_losses(self, number, hour, sec):
        dss = self.dss
        data_powers_losses = list()

        losses = dss.circuit.losses
        #losses = dss.circuit.line_losses

        # header = self.dss.monitors.header
        dss.monitors.name = self.monitor

        # Typical mode=65 mapping: Channel 1 (Ph1), Channel 3 (Ph2), Channel 5 (Ph3)
        p_phase1 = np.array(dss.monitors.channel(1))[number]
        p_phase2 = np.array(dss.monitors.channel(3))[number]
        p_phase3 = np.array(dss.monitors.channel(5))[number]

        q_phase1 = np.array(dss.monitors.channel(2))[number]
        q_phase2 = np.array(dss.monitors.channel(4))[number]
        q_phase3 = np.array(dss.monitors.channel(6))[number]
        print(f"q1:{q_phase1}; q2:{q_phase2}; q3:{q_phase3}; kvar")

        data_powers_losses.append({
            "cenario_id": self.cenario_id,
            "circuito": self.feeder,
            "controle_id": self.controle_id,
            "patamar": number,
            "hora": hour,
            "seg": sec,
            "p1": p_phase1,
            "p2": p_phase2,
            "p3": p_phase3,
            "q1": q_phase1,
            "q2": q_phase2,
            "q3": q_phase3,
            "p_losses": losses[0]/1000,
            "q_losses": losses[1]/1000,
        })

        self.__save_results_db("circuito", data_powers_losses)

    def _read_voltage_powers(self, number, hour, sec):
        data_bus = dict()
        data_bus_voltage_powers = list()

        for element in self.dss.circuit.elements_names:
            if element.lower().startswith(("line.smt", "line.sbt", "line.rbt")):
                self.dss.circuit.set_active_element(element)
                powers = self.dss.cktelement.powers
                half = len(powers) // 2

                kw_bus1 = powers[0:half:2]
                kvar_bus1 = powers[1:half:2]

                bus1_line = self.dss.cktelement.bus_names[0].split(".")[0]
                self.dss.circuit.set_active_bus(bus1_line)
                bus1_distance = self.dss.bus.distance
                bus1_nodes = self.dss.bus.nodes
                bus1_voltages_pu = self.dss.bus.vmag_angle_pu[::2]
                bus1_v_base = self.dss.bus.kv_base * 1000

                bus_tipo = 1 # BT
                if 1000 <= bus1_v_base <= 69000:
                    bus_tipo = 2 # MT
                elif bus1_v_base > 69000:
                    bus_tipo = 3 # AT

                for node, voltage, kw, kvar in zip(bus1_nodes, bus1_voltages_pu, kw_bus1, kvar_bus1):
                    key = (bus1_line, node)
                    if node == 4:
                        continue
                    if key not in data_bus:
                        data_bus[key] = {
                            "patamar": number,
                            "hour": hour,
                            "sec": sec,
                            "bus": bus1_line,
                            "node": node,
                            "vln_pu": voltage,
                            "v_base": bus1_v_base,
                            "tipo": bus_tipo,
                            "kw": kw,
                            "kvar": kvar,
                            "distance": bus1_distance
                        }

                    else:
                        data_bus[key]["kw"] += kw
                        data_bus[key]["kvar"] += kvar

        for values in data_bus.values():
            kw = values["kw"]
            kvar = values["kvar"]

            if kw >= 0.001 and abs(kvar) >= 0.001:
                fp = abs(kw) / math.sqrt(kw ** 2 + kvar ** 2)
                if kvar < 0 and not round(fp, 3) == 1:
                    fp = -fp
            else:
                fp = 1

            data_bus_voltage_powers.append({
                "cenario_id": self.cenario_id,
                "circuito": self.feeder,
                "controle_id": self.controle_id,
                "patamar": number,
                "hora": values["hour"],
                "seg": values["sec"],
                "bus": values["bus"],
                "node": values["node"],
                "vln_pu": values["vln_pu"],
                "v_base": values["v_base"],
                "tipo": values["tipo"],
                "kw": round(kw, 3),
                "kvar": round(kvar, 3),
                "fp": round(fp, 3),
                "distancia": round(values["distance"], 3)
            })

        self.__save_results_db("barra", data_bus_voltage_powers)

    def solve_circuit(self):
        data_cap = dict()
        count_cap = 0
        enable_cap = 0

        ini_tentativa = 1  # valor inicial para o loadmult
        max_tentativa = 20  # número de tentativas após não convergência
        patamar_ini = self.patamar_ini
        patamar_fim = self.patamar_fim

        self.loadmult_ini = self.dss.solution.load_mult
        for number in range(patamar_ini, patamar_fim):
            hour_previous = self.dss.solution.hour
            sec_previous = self.dss.solution.seconds

            self.dss.solution.solve()

            hour = self.dss.solution.hour
            sec = self.dss.solution.seconds

            status = self.dss.solution.converged
            if status == 0:
                print(f'OpenDSS: {self.feeder} - {self.cenario} - {self.controle} - NOT SOLVED to time {number}!')
                logging.info(f'OpenDSS: NOT SOLVED. '
                             f'Set {self.feeder}; {self.cenario}; {self.controle}; number: {number}, hour: {hour}, seconds: {sec}')

                sequencia = gerador_positivo_negativo()
                for tentativa in range(ini_tentativa, max_tentativa + ini_tentativa):
                    new_load_mult = self.loadmult_ini + next(sequencia) / 100

                    self.dss.text(f"set loadmult={new_load_mult}")
                    self.dss.text(f"set time = ({hour_previous}, {sec_previous})")

                    self.dss.solution.solve()
                    status = self.dss.solution.converged
                    if status == 0 and tentativa == max_tentativa:
                        print(f'❌ OpenDSS: File {self.dss_file} changed loadMult {new_load_mult} and NOT SOLVED - {self.feeder}; {self.cenario}; {self.controle}; Patamar:{number}, Hour: {hour}, Seconds: {sec}')
                        logging.info(f'OpenDSS: NOT SOLVED! - loadmult={new_load_mult} '
                                     f'Set {self.feeder}; {self.cenario}; {self.controle}; number: {number}, hour: {hour}, seconds: {sec}')
                        self.dss.text(f"set loadmult={self.loadmult_ini}")
                        self.__check_kv_base()

                    elif status == 0:
                        logging.info(f'OpenDSS: {self.feeder}; {self.cenario}; {self.controle}; - NOT SOLVED - Patamar:{number} - Tentativa:{tentativa} - loadmult_ini:{self.loadmult_ini} - new_load_mult:{new_load_mult}')
                        continue

                    else:
                        print(f'⚠️ OpenDSS: Feeder {self.feeder}; {self.cenario}; {self.controle}; changed loadMult {new_load_mult} and SOLVED - Patamar:{number}, Hour: {hour}, Seconds: {sec}')
                        logging.info(f'OpenDSS: {self.feeder}; {self.cenario}; {self.controle}; - SOLVED - Patamar:{number} - Tentativa:{tentativa} - loadmult_ini:{self.loadmult_ini} - new_load_mult:{new_load_mult}')
                        self.dss.text(f"set loadmult={self.loadmult_ini}")
                        self.__check_kv_base()
                        break

            print(f"\n{self.feeder}; {self.cenario}; {self.controle}; Patamar: {number}, Hour: {hour}, Seconds: {sec}")

            # Quantidade de capacitores
            if self.controle == 'Tensao':
                if count_cap == 0:
                    for capacitor_name in self.dss.capacitors.names:
                        self.dss.capacitors.name = capacitor_name
                        count_cap += 1

                        data_cap[capacitor_name] = {
                            "kvar_original": self.dss.capacitors.kvar,
                            "Step": 1
                        }

            # Verificação do funcionamento dos capacitores
            for capacitor_name in self.dss.capacitors.names:
                self.dss.capacitors.name = capacitor_name
                self.dss.circuit.set_active_element(f"capacitor.{self.dss.capacitors.name}")
                bus_capacitor = self.dss.cktelement.bus_names[0].split(".")[0]
                self.dss.circuit.set_active_bus(bus_capacitor)
                voltages_pu = self.dss.bus.vmag_angle_pu[::2]
                powers = self.dss.cktelement.powers
                kvar_bus1 = powers[1::2]

                if self.controle == 'Tensao':
                    capacitor_data = data_cap[capacitor_name]
                    kvar_step = capacitor_data["kvar_original"] / self.num_steps
                    step = capacitor_data["Step"]

                    for v_pu in voltages_pu:
                        if v_pu < self.on_VoltageControl:

                            new_kvar = kvar_step * step

                            if enable_cap != count_cap:
                                enable_cap += 1
                                self.enable_VoltageControl = True
                                self.__edit_capacitor(self.enable_VoltageControl, self.enable_TimeControl, capacitor_name)

                            if step <= self.num_steps:
                                if not step == self.num_steps:
                                    data_cap[capacitor_name]["Step"] += 1
                                self.dss.text(f'edit Capacitor.{capacitor_name} kvar={new_kvar}')

                            break

                        if not step == 0:
                            if v_pu > self.off_VoltageControl:
                                new_kvar = kvar_step * (step - 1)
                                data_cap[capacitor_name]["Step"] -= 1
                                self.dss.text(f'edit Capacitor.{capacitor_name} kvar={new_kvar}')
                                break

                    # Habilitado somente para o controle de tensão
                    print(f'{self.dss.capacitors.name}; {self.controle}:{self.dss.cktelement.is_enabled}; States:{self.dss.capacitors.states}; kvar:{(sum(kvar_bus1) * (self.dss.cktelement.is_enabled)):.2f} de {float(self.dss.capacitors.kvar)} ')

            if self.controle == 'Tempo':
                if hour == self.on_TimeControl:
                    self.enable_TimeControl = True
                    self.__edit_capacitor(self.enable_VoltageControl, self.enable_TimeControl, self.capacitor_name)

                if hour == self.off_TimeControl:
                    self.enable_TimeControl = False
                    self.__edit_capacitor(self.enable_VoltageControl, self.enable_TimeControl, self.capacitor_name)

            # Normalmente habilitado para a maioria dos controles
            if not self.controle == 'Tensao':
                print(f'{self.dss.capacitors.name}; {self.controle}:{self.dss.cktelement.is_enabled}; States:{self.dss.capacitors.states}; kvar:{(sum(kvar_bus1) * (self.dss.cktelement.is_enabled)):.2f} de {float(self.dss.capacitors.kvar)} ')

            if 1 <= hour <= 24 and sec == 0:
                path_dss = os.path.dirname(self.dss_file)
                file_exp = os.path.join(path_dss, f'{self.feeder}_{self.cenario}_{self.controle}_EXP_Profile_time_{hour}.CSV')
                self.dss.text(f"Export Profile Phases=All {file_exp}")
                self.__csv2db(file_exp, number, hour, sec)

            self._read_voltage_powers(number, hour, sec)
            self._read_powers_losses(number, hour, sec)
            self._read_cap(number, hour, sec, data_cap)

        print(f"✅ Alimentador:{self.feeder}; Cenário:{self.cenario}; Controle:{self.controle} processado com sucesso.")


@dataclass
class Task:
    utility: int
    feeder: str
    cenario: str
    controle: str
    month: int
    type_day: str
    num_patamares: int
    patamar_ini: int
    patamar_fim: int
    config: Dict


def find_file(filename: str, search_path: str):
    for root, dirs, files in os.walk(search_path):
        if filename in files:
            return Path(root) / filename
    return None

def run_feeder_mode(utility, substation, feeder, cenarios, controles, months, type_days, num_patamares, patamar_ini, patamar_fim, config):
    if num_patamares == 24:
        master_filename = f"{type_days[0]}_{months[0]}_Master_{utility}_{substation}_{feeder}.dss"
    else:
        master_filename = f"{type_days[0]}_{months[0]}_Master_{utility}_{substation}_{feeder}_{num_patamares}.dss"

    for cenario in cenarios:
        feeder_path = Path(config["feeder_path"]).resolve()
        master_path = find_file(master_filename, search_path=feeder_path)
        if master_path is None:
            print(f"❌ Master file não encontrado: {feeder_path} {master_filename}")
            return

        for controle in controles:

            simul = Feeder_Condition(
                            utility=utility,
                            substation=substation,
                            feeder=feeder,
                            dss_file=master_path,
                            num_patamares=num_patamares,
                            patamar_ini=patamar_ini,
                            patamar_fim=patamar_fim,
                            cenario=cenario,
                            controle=controle
                            )

            simul.solve_circuit()

def process_task(task: Task):
    utility = task.utility
    feeders = task.feeder
    cenarios = task.cenario
    controles = task.controle
    months = task.month
    type_days = task.type_day
    num_patamares = task.num_patamares
    patamar_ini = task.patamar_ini
    patamar_fim = task.patamar_fim
    config = task.config

    if isinstance(feeders, str):
        feeders = [feeders]
    if isinstance(cenarios, str):
        cenarios = [cenarios]
    if isinstance(controles, str):
        controles = [controles]
    if isinstance(months, (str, int)):
        months = [months]
    if isinstance(type_days, str):
        type_days = [type_days]

    for feeder in feeders:
        run_feeder_mode(
            utility=utility,
            substation=feeder[1:4], #config['feeder_path'].split(os.sep)[-1],
            feeder=feeder,
            cenarios=cenarios,
            controles=controles,
            months=months,
            type_days=type_days,
            num_patamares=num_patamares,
            patamar_ini=patamar_ini,
            patamar_fim=patamar_fim,
            config=config
        )

def to_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

def build_tasks_from_config(config: Dict) -> List[Task]:
    utility = config["utility"]
    feeders = to_list(config.get("feeder", []))
    cenarios = to_list(config.get("cenario", []))
    controles = to_list(config.get("controle", []))
    months = to_list(config.get("month", []))
    type_days = to_list(config.get("type_day", []))
    num_patamares = config["num_patamares"]
    patamar_ini = config["patamar_ini"]
    patamar_fim = config["patamar_fim"]

    tasks: List[Task] = []

    for feeder in feeders:
        for cenario in cenarios:
            for controle in controles:
                for m in months:
                    for td in type_days:
                        tasks.append(Task(
                            utility=int(utility),
                            feeder=str(feeder),
                            cenario=str(cenario),
                            controle=str(controle),
                            month=int(m),
                            type_day=str(td),
                            num_patamares=int(num_patamares),
                            patamar_ini=int(patamar_ini),
                            patamar_fim=int(patamar_fim),
                            config=config)
                        )

    return tasks

def main():
    application_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(application_path, "config_smartCAP.yml")

    inicio = time.time()

    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)["data_smartCAP"]

    tasks = build_tasks_from_config(config)
    if not tasks:
        print("Nenhuma tarefa criada. Verifique o config_smartRT.yml.")
        sys.exit(1)

    if config["multiprocess"]:
        cpu_cores = max(multiprocessing.cpu_count() - 11, 1)
        print(f"⚡ Utilizando {cpu_cores} processadores.")

        with multiprocessing.Pool(processes=cpu_cores) as pool:
            pool.map(process_task, tasks)

    else:
        for task in tasks:
            process_task(task)

    fim = time.time()
    tempo_total = fim - inicio

    horas = int(tempo_total // 3600)
    minutos = int((tempo_total % 3600) // 60)
    segundos = int(tempo_total % 60)

    print(f"Tempo total de execução: {horas:02d}h{minutos:02d}min{segundos:02d}seg")
    print("✅ Execução Completa")


if __name__ == '__main__':
    main()
