from setup_dinamico import (
    setup_dinamico_TSEA_iniciar,
    setup_dinamico_TSEA_configurar,
    setup_dinamico_TSEA_atualizar_pesos,
    setup_dinamico_TSEA_prever
)
import time
from py_dss_interface import DSS
import os
import pandas as pd
import numpy as np
import cmath
from dataclasses import dataclass, asdict
import logging
logging.basicConfig(filename='CTRL_SmartRT.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d,%H:%M:%S')

def convert2polar(real, imag):
    z = complex(real, imag)
    return cmath.polar(z)


def safe_divide(numerator, denominator):
    return numerator / denominator if denominator != 0 else 0


@dataclass
class Pesos:
    voltage_list: list
    tap: int
    reg_voltage: float
    vreg: float
    ptratio: float
    v_base: float
    v_reg_pu = float
    patamar: int = 0

    def __post_init__(self):
        self.v_reg_pu = (self.vreg * self.ptratio) / self.v_base


class SmartRT:
    def __init__(self, circuit, dss_file, bus_medicao, regcontrolname, num_patamatares=17280,
                 patamar_ini=1, patamar_fim=17280, usar_setup_dinamico=True):
        self.circuit = circuit
        self.dss_file = dss_file
        self.total_patamar = num_patamatares
        self.patamar_ini = patamar_ini
        self.paramar_fim = patamar_fim
        self.bus_medicao = list(bus_medicao)
        self.num_bus_medicao = len(bus_medicao)
        self.setup_dinamico = usar_setup_dinamico

        # pre-computes to speed up lookups
        self.bus_medicao_keys = [item.split('.') for item in self.bus_medicao]
        self.bus_medicao_lookup = {f"{bus.lower()}.{node}" for bus, node in self.bus_medicao_keys}
        self.bus_medicao_order_map = {f"{bus.lower()}.{node}": i for i, (bus, node) in enumerate(self.bus_medicao_keys)}

        self.regControlName = regcontrolname

        # incremental output configuration
        self.result_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados", self.circuit)
        self.path_result_bus = os.path.join(self.result_dir, "voltage_bus.csv")
        self.path_result_pesos = os.path.join(self.result_dir, "pesos.csv")
        self._bus_buffer = []
        self._flush_interval = 100  # flush to disk every 1000 patamares
        self._pesos_buffer = []

        # ensure DSS is ready
        self.dss = self._read_dss_file()

        # Check kv_base
        self.__check_kv_base()



    def _read_dss_file(self) -> DSS:
        """
        Leitura do arquivo 'master' sem executar o 'solve' e com os medidores desabilitados.
        :return: DSS
        """
        dss = DSS()
        dss.dssinterface.clear_all()
        dss.text(f"set Datapath = '{os.path.dirname(self.dss_file)}'")
        with open(os.path.join(self.dss_file), 'r') as file:
            for line_dss in file:
                if not (line_dss.startswith('!') or line_dss.startswith('\n') or line_dss.lower().startswith(
                        'clear')):
                    dss.text(line_dss.strip('\n'))
                if 'calc' in line_dss:
                    break

        dss.text("set mode = daily")
        dss.text("set controlmode = time")  # Todo avaliar resultado para Static
        dss.text("set tolerance = 0.0001")
        dss.text("set maxcontroliter = 100")
        dss.text("set maxiterations = 100")
        dss.text(f"Set stepsize = {86400 / self.total_patamar}s")
        dss.text("set number = 1")

        segundos_totais = int(self.patamar_ini * 86400 / self.total_patamar)
        minutos, segundos = divmod(segundos_totais, 60)
        horas, minutos = divmod(minutos, 60)
        total_sec = minutos * 60 + segundos

        dss.text(f"set time = ({horas}, {total_sec})")

        return dss

    def __check_kv_base(self):
        """
        Verifica a tensão de base definida pelo openDSS para as todas as barras conectadas
        no secundario dos transformadores.
        São obtidas as tensões de fase para a barra do secundario do TR e comparada com a informada pelo openDSS
        Em caso de diferença são localizadas todas barras conectadas no secundario do transformador e set o kv_base
        de todas as barras com o valor obtido da avaliação das conecções do transformador.
        :return:
        """
        # identifica a tensão de linha e de fase para cada transformador
        dss = self.dss
        tr_map = {}
        dss.transformers.first()
        vln = vll = None
        for _ in range(dss.transformers.count):
            dss.circuit.set_active_element(f"transformer.{dss.transformers.name}")
            tr_ph = dss.cktelement.num_phases
            if tr_ph == 3:
                dss.transformers.wdg = 2
                vll = dss.transformers.kv
                vln = dss.transformers.kv / np.sqrt(3)
            elif tr_ph == 1:
                num_wdg = dss.transformers.num_windings
                if num_wdg == 2:
                    dss.transformers.wdg = 2
                    if dss.transformers.is_delta:
                        vll = dss.transformers.kv
                        vln = vll / 2
                    else:
                        vln = dss.transformers.kv
                        vll = vln * 2
                elif num_wdg == 3:
                    dss.transformers.wdg = 2
                    vln = dss.transformers.kv
                    vll = 2 * vln

            tr_map[dss.transformers.name] = (round(vll, 3), round(vln, 3))

            bus_name = dss.cktelement.bus_names
            element_name = dss.cktelement.name
            dss.circuit.set_active_bus(bus_name[1])
            bus_name1 = dss.bus.name
            kv_base = dss.bus.kv_base
            # Verifica se ha diferença entre o calculado e o descrito pelo opnDSS
            if round(vln, 3) != round(kv_base, 3):
                print(f'{element_name}: {bus_name1}: {kv_base}: {vln}')
                # todo testar para ver se setar a tensão de linha e a tensão de fase fazem diferença !!!!
                # dss.text(f'SetkVBase Bus={bus_name1} kVLL={vll}')
                dss.text(f'SetkVBase Bus={bus_name1} kVLN={vln}')
                print(f'Valor alterado: {dss.cktelement.bus_names[1]} - kvbase:{dss.bus.kv_base}')

                # Localozar o transformador que foi alterado o valor de kvbase atraves da topologia
                dss.topology.first()
                while True:
                    indx = dss.topology.active_branch
                    indx_level = dss.topology.active_level
                    branch_name = dss.topology.branch_name
                    if branch_name == element_name:
                        dss.circuit.set_active_element(element_name)
                        dss.circuit.set_active_bus(dss.cktelement.bus_names[1])
                        # encontrou o transformador que foi alterado com setkvbase
                        break
                    index_branch = dss.topology.forward_branch()

                # busca os ramais conectados neste transformador
                while True:
                    index_branch_2 = dss.topology.next()
                    indx_level_2 = dss.topology.active_level
                    branch_name_2 = dss.topology.branch_name
                    if not dss.topology.branch_name.startswith(('Line.sbt', 'Line.rbt')):
                        print('\n Proximo transformador !!! \n')
                        break
                    # sekvbase aqui
                    dss.circuit.set_active_element(branch_name_2)
                    dss.circuit.set_active_bus(dss.cktelement.bus_names[1])
                    kv_base_2 = dss.bus.kv_base
                    print(f'{branch_name_2}: {dss.cktelement.bus_names}: {kv_base_2}')
                    dss.text(f'SetkVBase Bus={bus_name1} kVLL={vll}')
                    dss.text(f'SetkVBase Bus={bus_name1} kVLN={vln}')
                    print(f'Valor alterado: {dss.cktelement.bus_names[1]} - kvbase:{dss.bus.kv_base}')
            dss.transformers.next()

        self._transformer_kv_map = tr_map

    def configure(self):
        num_entradas = self.num_bus_medicao
        algoritmo_de_controle = setup_dinamico_TSEA_iniciar(num_entradas=num_entradas)

        setup_dinamico_TSEA_configurar(limite_inf_tensao_saida=0.93,
                                       limite_sup_tensao_saida=1.05,
                                       limites_inf_pontos=[0.93] * num_entradas,
                                       limites_sup_pontos=[1.05] * num_entradas)
        return algoritmo_de_controle

    def _set_pesos(self, patamar_rows):
        # patamar_rows: lista de dicts contendo as tensões do patamar atual
        if isinstance(patamar_rows, pd.DataFrame):
            df_patamar_voltage = patamar_rows.copy()
        else:
            df_patamar_voltage = pd.DataFrame(patamar_rows)

        if df_patamar_voltage.empty:
            print("_set_pesos: patamar vazio.")
            return None

        # normaliza colunas
        df_patamar_voltage.loc[:, 'bus'] = df_patamar_voltage['bus'].astype(str).str.lower()
        df_patamar_voltage.loc[:, '_bus_node'] = df_patamar_voltage['bus'] + '.' + df_patamar_voltage['nodes'].astype(str)

        # tensões nos barramentos selecionados
        df_bus_medicao = df_patamar_voltage[df_patamar_voltage['_bus_node'].isin(self.bus_medicao_lookup)].copy()

        if df_bus_medicao.shape[0] < len(self.bus_medicao):
            print(f"Barra não encontrada! Verificar a lista de barras fornecida.")
            exit()

        self.dss.regcontrols.name = self.regControlName[0]
        if self.dss.regcontrols.name == self.regControlName[0]:
            tap_reg = self.dss.regcontrols.tap_number
            winding = self.dss.regcontrols.winding
            rreg = self.dss.regcontrols.reverse_vreg
            fvreg = self.dss.regcontrols.forward_vreg
            pt_ratio_reg = self.dss.regcontrols.pt_ratio
            self.dss.transformers.name = self.dss.regcontrols.transformer
            bus_reg_trafo = self.dss.cktelement.bus_names[1].split('.')[0]
            node_reg_trafo = self.dss.cktelement.bus_names[1].split('.')[1]
            self.dss.circuit.set_active_bus(bus_reg_trafo)
            v_base = self.dss.bus.kv_base * 1000

            # tensão no regulador selecionado
            volt_bus_reg = df_patamar_voltage.loc[
                (df_patamar_voltage['bus'] == bus_reg_trafo.lower()) & (df_patamar_voltage['nodes'] == node_reg_trafo)]

            # garantir a ordem das barras igual a lista de entrada das barras de medicao
            df_bus_medicao.loc[:, 'bus_sort'] = df_bus_medicao['_bus_node'].map(self.bus_medicao_order_map)
            df_bus_medicao = df_bus_medicao.sort_values('bus_sort').drop(columns=['bus_sort', '_bus_node'])

            # tenta extrair patamar do dataframe
            try:
                pat_val = int(df_patamar_voltage['patamar'].iat[0])
            except Exception:
                pat_val = 0

            pesos = Pesos(voltage_list=df_bus_medicao['vln_pu'].tolist(), tap=tap_reg, patamar=pat_val,
                          reg_voltage=volt_bus_reg['vln_pu'].values[0], vreg=fvreg, ptratio=pt_ratio_reg, v_base=v_base)
            # print('Determinacao dos pesos ok. ')
            return pesos
        else:
            print(f'Regulador nao encontrado!')
            return None

    def _flush_bus_buffer(self):
        # escreve buffer acumulado em disco e limpa o buffer
        if not self._bus_buffer:
            return
        os.makedirs(self.result_dir, exist_ok=True)
        write_header = not os.path.exists(self.path_result_bus)
        df_chunk = pd.DataFrame(self._bus_buffer)
        df_chunk.to_csv(self.path_result_bus, mode='a', header=write_header, index=False)
        self._bus_buffer.clear()

    def _flush_pesos_buffer(self):
        # escreve buffer de pesos acumulado em disco e limpa o buffer
        if not self._pesos_buffer:
            return
        os.makedirs(self.result_dir, exist_ok=True)
        write_header = not os.path.exists(self.path_result_pesos)
        df_chunk = pd.DataFrame([asdict(p) if hasattr(p, '__dataclass_fields__') else p for p in self._pesos_buffer])
        df_chunk.to_csv(self.path_result_pesos, mode='a', header=write_header, index=False)
        self._pesos_buffer.clear()

    def _save_results(self):
        # save pesos results
        # flush any remaining pesos buffer and ensure directory exists
        os.makedirs(self.result_dir, exist_ok=True)
        self._flush_pesos_buffer()

        # save voltage_bus_results: if we used incremental flush, the CSV already exists on disk
        if hasattr(self, 'all_bus_kv') and isinstance(self.all_bus_kv, pd.DataFrame):
            self.all_bus_kv.to_csv(self.path_result_bus, index=False)

    def solve_circuit(self):
        total_number = self.total_patamar
        patamar_ini = self.patamar_ini
        patamar_fim = self.paramar_fim

        # start with a fresh output file for incremental writes
        if os.path.exists(self.path_result_bus):
            try:
                os.remove(self.path_result_bus)
            except OSError:
                pass
        if os.path.exists(self.path_result_pesos):
            try:
                os.remove(self.path_result_pesos)
            except OSError:
                pass

        for number in range(patamar_ini, patamar_fim + 1):

            hour =  self.dss.solution.hour
            sec = self.dss.solution.seconds
            print(f"Patamar:{number}, hour: {hour}, seconds: {sec}")

            self.dss.solution.solve()
            status = self.dss.solution.converged
            if status == 0:
                print(f'OpenDSS: File {self.dss_file} not solved to time {number}!')
                # tentar novamente com loadmult
                self.dss.text(f"set loadmult=1.01")
                self.dss.text(f"set time = ({hour}, {sec})")
                print(f"Patamar:{number}, hour: {hour}, seconds: {sec}")
                self.dss.solution.solve()
                self.dss.text(f"set loadmult=1.0")
                status = self.dss.solution.converged
                if status == 0:
                    print(f'OpenDSS: File {self.dss_file} alter loadMult 1.01 and not solved to time {number}!')

                    # tentar novamete aumentando um pouco mais a carga.
                    self.dss.text(f"set loadmult=1.02")
                    self.dss.text(f"set time = ({hour}, {sec})")
                    self.dss.solution.solve()
                    self.dss.text(f"set loadmult=1.0")
                    status = self.dss.solution.converged
                    if status == 0:
                        logging.info(
                            f'OpenDSS: File {self.dss_file} NOT solved! - loadmult=1.02'
                            f'Set number: {number}, hour: {hour}, seconds: {sec}, event: {self.dss.solution.event_log}')
                        continue
                    else:
                        logging.info(f'OpenDSS: File {self.dss_file} SOLVED alter loadMult 1.02  '
                            f'Set number: {number}, hour: {hour}, seconds: {sec}, event: {self.dss.solution.event_log}')
                        print(f'OpenDSS: File {self.dss_file} alter loadMult 1.02 and solved to time {number}!')
                else:
                    logging.info(
                        f'OpenDSS: File {self.dss_file} SOLVED alter loadMult 1.01! '
                        f'Set number: {number}, hour: {hour}, seconds: {sec}, {self.dss.solution.event_log}')

                    print(f'OpenDSS: File {self.dss_file} alter loadMult 1.01 and solved to time {number}!')


            current_voltage_rows = []
            for bus_name in self.dss.circuit.nodes_names:
                active_bus, bus_node = bus_name.split('.', 1)
                self.dss.circuit.set_active_bus(active_bus)
                nodes = self.dss.bus.nodes

                if bus_node == '4':
                    continue

                num_nodes = len(self.dss.bus.vll) // 2
                if num_nodes == 1:
                    pos = 0
                    vll_1 = 0
                    vll_pu_1 = 0
                else:
                    pos = nodes.index(int(bus_node))
                    vll_1 = round(convert2polar(self.dss.bus.vll[pos * 2], self.dss.bus.vll[(pos * 2) + 1])[0], 5)
                    #vll_1 = np.float32(vll_1)
                    vll_pu_1 = round(convert2polar(self.dss.bus.pu_vll[pos * 2], self.dss.bus.pu_vll[(pos * 2) + 1])[0], 5)
                    #vll_pu_1 = np.float32(vll_pu_1)

                vln_1 = round(convert2polar(self.dss.bus.voltages[pos * 2], self.dss.bus.voltages[(pos * 2) + 1])[0], 5)
                #vln_1 = np.float32(vln_1)
                vln_pu_1 = round(convert2polar(self.dss.bus.pu_voltages[pos * 2], self.dss.bus.pu_voltages[(pos * 2) + 1])[0], 5)
                #vln_pu_1 = np.float32(vln_pu_1)

                current_voltage_rows.append({
                    "patamar": number,
                    "bus": f"{bus_name.split('.')[0]}".lower(),
                    "nodes": bus_node,
                    "vll": vll_1,
                    "vln": vln_1,
                    "vll_pu": vll_pu_1,
                    "vln_pu": vln_pu_1,
                    "kv_base": int(self.dss.bus.kv_base * 1000)
                })

            # append to buffer and flush in blocks
            self._bus_buffer.extend(current_voltage_rows)
            if number % self._flush_interval == 0:
                self._flush_bus_buffer()


            # Determina e armazena pesos para ESTE patamar (histórico completo)
            set_pesos = self._set_pesos(current_voltage_rows)
            if set_pesos is not None:
                # buffer e gravação incremental de pesos (não manter em memória)
                self._pesos_buffer.append(asdict(set_pesos))
                if len(self._pesos_buffer) >= self._flush_interval:
                    self._flush_pesos_buffer()
                print(set_pesos)

            # controle para inserir ou remover o setup dinamico da simulação
            if self.setup_dinamico:

                # atualiza o setup dinamico a cada 3 patamares
                if (number-1) % 3 == 0:
                    setup_dinamico_TSEA_atualizar_pesos(tensao_saida=set_pesos.reg_voltage,
                                                        tenssoes_pontos=set_pesos.voltage_list,
                                                        tap_atual=set_pesos.tap)

                # previsao do setup dinamico para o proximo patamar
                if number % 48 == 0 and set_pesos is not None:
                    setpoint = set_pesos.v_reg_pu
                    result_set_point = setup_dinamico_TSEA_prever(tensao_saida=set_pesos.reg_voltage,
                                                                  entradas=set_pesos.voltage_list,
                                                                  setpoint_atual=setpoint )

                    # valor do vreg do regulador de tensão
                    new_vreg = result_set_point * set_pesos.v_base / set_pesos.ptratio

                    # set the same vreg for all regulators
                    for reg_name in self.regControlName:
                        self.dss.regcontrols.name = reg_name
                        print(f'Regulador:{reg_name} setpoint:{result_set_point} New:{new_vreg} Old:{self.dss.regcontrols.forward_vreg}')
                        self.dss.regcontrols.forward_vreg = new_vreg

        # flush any remaining buffered rows
        self._flush_bus_buffer()
        self._flush_pesos_buffer()

        # Do not load the full voltage_bus.csv into memory to save RAM.
        # The incremental CSV remains on disk at self.path_result_bus for post-processing.
        self.all_bus_kv = None


if __name__ == '__main__':

    dss_file = r'C:\pastaD\TSEA\SmartRT\cenarios\RMTQ1302_TSEA\DU_7_Master_391_MTQ_RMTQ1302_17280_TSEA.dss'
    circuito = 'RMTQ1302'
    # Os pontos de medição devem ser da mesma fase.
    pontos_de_medicao = ['mt4339274745933283mt02.1', 'mt4291205645697419mt02.1', 'mt4294449845693038mt02.1',
                         'mt4283709245476469mt02.1', 'BT430501424549936MT02.1' ]

                         # 'bt4295442945257362mt02.1'] #    , 'mt4279615845183301mt02.1']

    regcontrol = 'creg_295rt000020129c' # Atencao: node 1!
    # O primeiro regulador da lista deve ter a mesma fase das barras de medição selecionadas.
    regcontrol = ['creg_295rt000020129c', 'creg_295rt000020129a', 'creg_295rt000020129b']

    pontos_de_medicao = ['BT4274688645149945MT02.1', 'MT434452545570824MT02.1', 'BT4361929845347146MT02.1',
                         'mt4283709245476469mt02.1', 'BT430501424549936MT02.1']



    num_patamatares = 17280             # numero total de patamares da simulação
    patamar_ini = 0                 # 3600   # numero de patamares - converter a hora de inicio da simulação em patamares
    patamar_fim = 17280             # 5000   # converter a hora de fim da simulação em patamares

    proc_time_ini = time.time()

    simul = SmartRT(circuit=circuito,
                    dss_file=dss_file,
                    bus_medicao=pontos_de_medicao,
                    num_patamatares=num_patamatares,
                    regcontrolname= regcontrol,
                    patamar_ini=patamar_ini,
                    patamar_fim=patamar_fim,
                    usar_setup_dinamico = True)

    ctr = simul.configure()

    simul.solve_circuit()

    print(f"Processo concluído em {time.time() - proc_time_ini}")
