import pandas as pd
import numpy as np
import polars as pl
import time
import  os
import matplotlib
from pathlib import Path

import yaml
from seaborn._core import subplots

matplotlib.use('TKAgg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
import pyarrow
from dataclasses import dataclass

pd.set_option('display.max_rows', None)

@dataclass
class Analisys:
    data_path: str
    pesos_data: str
    data_dir = str
    data_file = str
    data_circuit = str
    pesos_data_path= str

    def __post_init__(self):
        full_path = Path(self.data_path)
        self.data_dir = full_path.parent
        self.data_file = full_path.name
        self.data_circuit = full_path.parts[-2]
        self.pesos_data_path  = os.path.join(self.data_dir, self.pesos_data)


    def plot_voltage_by_pesos(self, buses_phases):

        df_all = (pl.scan_csv(self.pesos_data_path)
                  .select('patamar', 'voltage_list_faseA', 'voltage_list_faseB', 'voltage_list_faseC')
                  #.filter((pl.col("patamar") >= 0) & (pl.col("patamar") < 1000) )
                  )

        dados = df_all.collect().to_pandas()
        dados_plot = []
        for index, buses_phase in enumerate(buses_phases):
            dados_fase = pd.DataFrame(dados.iloc[:, index+1]
                                    .str.replace('[', '', regex=False)
                                    .str.replace(']', '', regex=False))
            dados_fase[buses_phase] = dados_fase[dados_fase.columns[0]].str.split(',', expand=True)
            dados_fase = dados_fase.drop(columns=[dados_fase.columns[0]])
            dados_fase = dados_fase.astype(float)
            dados_plot.append(dados_fase)

        fases = ['fase A', 'fase B', 'fase C']

        # plot gráficos
        sup_limit = 1.05
        inf_limit = 0.95
        inf_limit_bt = 0.93
        lw = 0.75
        fig, axes = plt.subplots(nrows=3, ncols=1, sharey=True , figsize=(10, 9))

        dados_plot[0].plot(ax=axes[0], title=f"Voltage Bus - {fases[0]}").legend(fontsize=8)
        axes[0].axhline(y=1.05, color='r', linestyle='--', alpha=0.8, label='mt_over_crit')
        axes[0].axhline(y=0.93, color='r', linestyle='--', alpha=0.8, label='mt_under_prec')
        axes[0].axhline(y=0.90, color='r', linestyle='--', alpha=0.8, label='mt_under_crit')
        axes[0].axhline(y=1.06, color='g', linestyle='--', alpha=0.8, label='bt_over_crit')
        axes[0].axhline(y=1.047, color='g', linestyle='--', alpha=0.8, label='bt_over_prec')
        axes[0].axhline(y=0.866, color='g', linestyle='--', alpha=0.8, label='bt_under_prec')  # 110/127
        axes[0].axhline(y=0.92, color='g', linestyle='--', alpha=0.8, label='bt_under_crit')

        dados_plot[1].plot(ax=axes[1], title=f"Voltage Bus - {fases[1]}").legend(fontsize=8)
        axes[1].axhline(y=1.05, color='r', linestyle='--', alpha=0.8, label='mt_over_crit')
        axes[1].axhline(y=0.93, color='r', linestyle='--', alpha=0.8, label='mt_under_prec')
        axes[1].axhline(y=0.90, color='r', linestyle='--', alpha=0.8, label='mt_under_crit')
        axes[1].axhline(y=1.06, color='g', linestyle='--', alpha=0.8, label='bt_over_crit')
        axes[1].axhline(y=1.047, color='g', linestyle='--', alpha=0.8, label='bt_over_prec')
        axes[1].axhline(y=0.866, color='g', linestyle='--', alpha=0.8, label='bt_under_prec')
        axes[1].axhline(y=0.92, color='g', linestyle='--', alpha=0.8, label='bt_under_crit')

        dados_plot[2].plot(ax=axes[2], title=f"Voltage Bus - {fases[2]}").legend(fontsize=8)
        axes[2].axhline(y=1.05, color='r', linestyle='--', alpha=0.8, label='mt_over_crit')
        axes[2].axhline(y=0.93, color='r', linestyle='--', alpha=0.8, label='mt_under_prec')
        axes[2].axhline(y=0.90, color='r', linestyle='--', alpha=0.8, label='mt_under_crit')
        axes[2].axhline(y=1.06, color='g', linestyle='--', alpha=0.8, label='bt_over_crit')
        axes[2].axhline(y=1.047, color='g', linestyle='--', alpha=0.8, label='bt_over_prec')
        axes[2].axhline(y=0.866, color='g', linestyle='--', alpha=0.8, label='bt_under_prec')
        axes[2].axhline(y=0.92, color='g', linestyle='--', alpha=0.8, label='bt_under_crit')

        #plt.title(f"Voltage Bus - {self.data_circuit}")
        plt.xlabel(f"Time steps")
        plt.tight_layout()  # Prevents label overlapping
        plt.grid(axis='y')
        plt_path = os.path.join(self.data_dir, f"Voltage_bus_fases.png")
        plt.savefig(plt_path)

    """
    def plot_voltage(self, buses_phases):
        list_buses = []
        list_nodes = []
        # scan_csv doesn't load the file; it creates a plan
        df_all = pl.scan_csv(self.data_path).select('patamar', 'bus', 'nodes', 'vln_pu')

        fases = ['faseA', 'faseB', 'faseC']

        for buses_phase in buses_phases:
            for bus_phase in buses_phase:
                bus_atual, bus_node = bus_phase.lower().split('.', 1)
                list_buses.append(bus_atual)
                list_nodes.append(int(bus_node) )

            df_filtros = pl.LazyFrame({
                "bus": list_buses,
                "nodes": list_nodes
            })

            df = df_all.join(df_filtros,
                on=["bus", "nodes"],
                how="inner"
            )

            df = df.select(["patamar", "bus", "vln_pu"]).filter(pl.col("patamar") >= 0 &
                                                                (pl.col("patamar") < 10 ))
            dados = df.collect().to_pandas()
            dados = dados.pivot(index='patamar', columns='bus', values='vln_pu')


        for index, fase in enumerate(fases):
            df = df_all.filter(pl.col("bus").is_in(buses) & (pl.col("nodes")==(index+1) ) )
            df = df.select(["patamar", "bus", "vln_pu"])
            dados = df.collect().to_pandas()
            dados = dados.pivot(index='patamar', columns='bus', values='vln_pu')

            #print(dados)
            ax = dados.plot( y=buses, figsize=(7, 5))
            plt.title(f"BUS voltage: - {self.data_circuit} - {fase}")
            plt.ylabel(f"Voltage (p.u.)")
            plt.xlabel(f"Time steps")
            plt.grid(axis='y')
            ax.legend(loc='upper right', bbox_to_anchor=(1, 1), fontsize='small')
            #ax.xaxis.set_major_locator(ticker.MultipleLocator(690))
            plt_path = os.path.join(self.data_dir, f"bus_medicoes_voltages_{fase}.png")
            #plt.savefig(plt_path, dpi=300, bbox_inches='tight', transparent=False)
            plt.savefig(plt_path)
            plt.show()
    """

    def plot_taps(self):
        df = pl.scan_csv(self.pesos_data_path)
        df = df.select(["patamar", "vreg", "tap_faseA", "tap_faseB", "tap_faseC",
                        "reg_voltage_faseA", "reg_voltage_faseB", "reg_voltage_faseC"])
        dados = df.collect().to_pandas()

        fases = ['faseA','faseB','faseC']
        tap_max = int(dados[['tap_faseA','tap_faseB','tap_faseC']].max().max() + 1 )
        tap_min = int(dados[['tap_faseA', 'tap_faseB', 'tap_faseC']].min().min() - 1 )
        vreg_max = dados["vreg"].max().max() * 1.1
        vreg_min = dados["vreg"].max().min() * 0.9
        reg_volt_max = round(dados[['reg_voltage_faseA', 'reg_voltage_faseB', 'reg_voltage_faseC']].max().max() * 1.02, 3)
        reg_volt_mim = round(dados[['reg_voltage_faseA', 'reg_voltage_faseB', 'reg_voltage_faseC']].min().min() * 0.95, 3)

        for fase in fases:
            fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(10, 8))

            dados[f"tap_{fase}"].plot(ax=axes[0], ylim=(tap_min , tap_max), title=f"TAP Change {fase}", color='blue')
            dados["vreg"].plot(ax=axes[1], ylim=(vreg_min , vreg_max), title="Vref", color='red')
            dados[f"reg_voltage_{fase}"].plot(ax=axes[2],  ylim=(reg_volt_mim , reg_volt_max), title="Vreg", color='green')

            plt.xlabel(f"Time steps")
            plt.tight_layout()  # Prevents label overlapping
            plt.grid(axis='y')
            plt_path = os.path.join(self.data_dir, f"tap_change_{fase}.png")
            plt.savefig(plt_path)

    def plot_results(self, dados):
        circuit = self.data_circuit
        # plt_path_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados", circuit)
        plt_path_base = self.data_dir
        #pdf = dados.to_pandas()
        pdf = dados
        mt_df = pdf[['mt_undervolt_crit', 'mt_undervolt_prec', 'mt_overvolt_crit']].copy()
        bt_df = pdf[['bt_undervolt_prec', 'bt_undervolt_crit', 'bt_overvolt_prec', 'bt_overvolt_crit']].copy()

        counts_bt_under_prec_perc = bt_df['bt_undervolt_prec'] / pdf['cnt_bt_bus'][0] * 100
        counts_bt_under_crit_perc = bt_df['bt_undervolt_crit'] / pdf['cnt_bt_bus'][0] * 100
        counts_bt_over_prec_perc = bt_df['bt_overvolt_prec'] / pdf['cnt_bt_bus'][0] * 100
        counts_bt_over_crit_perc =  bt_df['bt_overvolt_crit'] / pdf['cnt_bt_bus'][0] * 100
        bt_df_under = pd.DataFrame({'bt_undervoltage_prec': counts_bt_under_prec_perc,
                                   'bt_undervoltage_crit': counts_bt_under_crit_perc})

        bt_df_over = pd.DataFrame({'bt_overvoltage_prec': counts_bt_over_prec_perc,
                                   'bt_overvoltage_crit': counts_bt_over_crit_perc})

        counts_mt_under_prec_perc = mt_df['mt_undervolt_prec'] / pdf['cnt_mt_bus'][0] * 100
        counts_mt_under_crit_perc = mt_df['mt_undervolt_crit'] / pdf['cnt_mt_bus'][0] * 100
        counts_mt_over_crit_perc = mt_df['mt_overvolt_crit'] / pdf['cnt_mt_bus'][0] * 100
        mt_df_perc = pd.DataFrame({'mt_undervoltage_prec': counts_mt_under_prec_perc,
                                   'mt_undervoltage_crit': counts_mt_under_crit_perc,
                                   'mt_overvoltage_crit': counts_mt_over_crit_perc})

        espacamento = 690
        if not bt_df.empty:
            max_under = bt_df_under.max().sum()
            max_over = bt_df_over.max().sum()
            escala_max = int(max(max_under, max_over) * 1.1)

            ax = bt_df.plot(kind='bar', stacked=True)
            plt.title(f"BUS Violation : {circuit}")
            plt.ylabel(f"Number")
            plt.xlabel(f"Time steps")
            plt.grid(axis='y')
            ax.xaxis.set_major_locator(ticker.MultipleLocator(espacamento))
            plt_path = os.path.join(plt_path_base, "bt_voltages.png")
            plt.savefig(plt_path, dpi=600, bbox_inches='tight', transparent=False)
            plt.show(block=False)

            # grafico de porcentagem - undervoltage
            ax = bt_df_under.plot(kind='bar', stacked=True)
            plt.title(f"BUS Violation: Undervoltage - {circuit}")
            plt.ylabel(f"Number (%)")
            plt.xlabel(f"Time steps")
            plt.grid(axis='y')
            ax.xaxis.set_major_locator(ticker.MultipleLocator(espacamento))
            plt_path = os.path.join(plt_path_base, "bt_voltages_under.png")
            plt.savefig(plt_path, dpi=600, bbox_inches='tight', transparent=False)
            plt.show(block=False)

            # grafico de porcentagem - overvoltage
            ax = bt_df_over.plot(kind='bar', stacked=True)
            plt.title(f"BUS Violation: Overvoltage - {circuit}")
            plt.ylabel(f"Number (%)")
            plt.xlabel(f"Time steps")
            plt.grid(axis='y')
            ax.xaxis.set_major_locator(ticker.MultipleLocator(espacamento))
            plt_path = os.path.join(plt_path_base, "bt_voltages_over.png")
            plt.savefig(plt_path, dpi=600, bbox_inches='tight', transparent=False)
            plt.show(block=False)

        else:
            print("Sem violação de tensão BT.")

        if not mt_df.empty :
            ax = mt_df.plot(kind='bar', stacked=True)
            plt.title(f"BUS Violation : {circuit}")
            plt.ylabel(f"Number")
            plt.xlabel(f"Time")
            ax.xaxis.set_major_locator(ticker.MultipleLocator(espacamento))
            plt_path = os.path.join(plt_path_base, "mt_voltages.png")
            plt.savefig(plt_path, dpi=600, bbox_inches='tight', transparent=False)
            plt.show(block=False)

            # grafico de porcentagem
            ax = mt_df_perc.plot(kind='bar', stacked=True)
            plt.title(f"BUS Violation : {circuit}")
            plt.ylabel(f"Number (%)")
            plt.xlabel(f"Time")
            ax.xaxis.set_major_locator(ticker.MultipleLocator(espacamento))
            plt_path = os.path.join(plt_path_base, "mt_voltages_perc.png")
            plt.savefig(plt_path, dpi=600, bbox_inches='tight', transparent=False)
            plt.show(block=False)
        else:
            print("Sem violação de tensão MT.")


    def polar_read_csv(self):
        proc_time_ini = time.time()
        results_combined = pd.DataFrame()

        bloco_ini = -1
        points = np.linspace(0, 17280, 5)
        points = points[1:]
        # Processa os dados em bloco - evita estouro de memoria
        for bloco in points:
            #bloco = 10   # só para teste... remover!!!
            # scan_csv doesn't load the file; it creates a plan
            lazy_df = ((pl.scan_csv(self.data_path).select(["patamar", "bus", "nodes", "kv_base", "vln_pu", "vln"])).with_columns([
                             pl.col("bus").cast(pl.Categorical),
                             pl.col("patamar").cast(pl.UInt16),
                             pl.col("kv_base").cast(pl.Float32),
                             pl.col("vln_pu").cast(pl.Float32),
                             pl.col("vln").cast(pl.Float32),
                      ])
                       .filter((pl.col("patamar") > bloco_ini) &( pl.col("patamar") <= bloco))
                      )

            #results = lazy_df.collect(engine="streaming").to_pandas()
            #print('')
            # ------------------------------------------------------------------
            # Obtém o MAIOR valor por NODE dentro de cada patamar
            # ------------------------------------------------------------------
            node_max_df = (
                lazy_df
                .group_by(["patamar", "bus",])
                .agg(
                    pl.col("kv_base").first().alias("kv_base"),
                    pl.col("vln_pu").max().alias("max_vln_pu"),
                    pl.col("vln_pu").min().alias("min_vln_pu"),
                    pl.col("vln").max().alias("max_vln"),
                    pl.col("vln").min().alias("min_vln"),
                )
            )

            #results = node_max_df.collect(engine="streaming").to_pandas()
            #print('')

            # ------------------------------------------------------------------
            # Calcula os indicadores
            # ------------------------------------------------------------------
            filtered_df = (
                node_max_df
                .group_by("patamar")
                .agg(
                    ((pl.col("kv_base") > 1000) & (pl.col("max_vln_pu") > 1.05)).sum().alias("mt_overvolt_crit"),
                    ((pl.col("kv_base") > 1000) & ((pl.col("min_vln_pu") >= 0.90) & (pl.col("min_vln_pu") < 0.93))).sum().alias("mt_undervolt_prec"),
                    ((pl.col("kv_base") > 1000) & (pl.col("min_vln_pu") < 0.90)).sum().alias("mt_undervolt_crit"),

                    ((pl.col("kv_base") == 127) & ((pl.col("min_vln") > 0.2) & (pl.col("min_vln") < 110)) |
                     (pl.col("kv_base") == 120) & ((pl.col("min_vln") > 0.2) & (pl.col("min_vln") < 104))
                     ).sum().alias("bt_undervolt_crit"),
                    ((pl.col("kv_base") == 127) & ((pl.col("min_vln") >= 110) & (pl.col("min_vln") < 117)) |
                     (pl.col("kv_base") == 120) & ((pl.col("min_vln") >= 104) & (pl.col("min_vln") < 110))
                     ).sum().alias("bt_undervolt_prec"),
                    ((pl.col("kv_base") == 127) & ((pl.col("max_vln") > 133) & (pl.col("max_vln") <= 135)) |
                     (pl.col("kv_base") == 120) & ((pl.col("max_vln") > 126) & (pl.col("max_vln") <= 127))
                     ).sum().alias("bt_overvolt_prec"),
                    ((pl.col("kv_base") == 127) & (pl.col("max_vln") >= 135) |
                     (pl.col("kv_base") == 120) & (pl.col("max_vln") >= 127)
                     ).sum().alias("bt_overvolt_crit"),

                    (pl.col("kv_base") < 1000).sum().alias("cnt_bt_bus"),
                    (pl.col("kv_base") > 1000).sum().alias("cnt_mt_bus"),

                     )
                .sort(pl.col("patamar").cast(pl.UInt16), descending=False)
            )

            results  = filtered_df.collect(engine="streaming").to_pandas()
            results_combined = pd.concat([results_combined, results], axis=0)

            # print(f"Result:   {results}")
            print(f"Processo concluído para o bloco: {bloco} em {time.time() - proc_time_ini}")
            bloco_ini = bloco
        results_combined.reset_index(drop=True, inplace=True)
        return results_combined

    def plot_perfil_tensao(self,
            path_file,
            col_x1=" Distance1",
            col_y1=" puV1",
            col_x2=" Distance2",
            col_y2=" puV2",
            titulo=f"Perfil de Tensão do Circuito",
            figsize=(10, 5),
            mostrar_nos=False,
    ):

        for file in Path(path_file).glob('*Profile*.csv'):
            print(file.name)
            titulo = f"Perfil de Tensão - {self.data_circuit} - Hora: {file.name.split("_")[-1].split('.')[0]}h"
            df = pd.read_csv(file.absolute())

            plt.figure(figsize=figsize)
            color = ['blue', 'red', 'black']
            linetype = ['-',':', ':','--']
            super_limite = 1.1
            inf_limite = 0.80
            # Desenha cada segmento
            for _, row in df.iterrows():
                x = [row[col_x1], row[col_x2]]
                y = [row[col_y1], row[col_y2]]

                idcolor = row[' Color']
                tipo = row[' Linetype']

                # verifica o maior valor para a média tensão e altera a escala do gráfico
                if tipo == 0:
                    if row[col_y1] > super_limite:
                        super_limite = row[col_y1] * 1.03
                    if row[col_y2] > super_limite:
                        super_limite = row[col_y2] * 1.03

                lw = 1.5
                if tipo == 2:
                    lw = 0.75
                plt.plot(x, y, color=color[idcolor-1], linestyle=linetype[tipo], linewidth=lw)

                # Opcional: mostrar pontos
                if mostrar_nos:
                    plt.scatter(x, y, color="red", s=15)

            # Configurações do gráfico
            plt.title(titulo, fontsize=14)
            plt.xlabel("Distância (km)", fontsize=12)
            plt.ylabel("Tensâo (pu)", fontsize=12)
            plt.axhline(y=1.05, color='r', linestyle='--', label='mt_over_crit')
            plt.axhline(y=0.93, color='r', linestyle='--', label='mt_under_prec')
            plt.axhline(y=0.90, color='r', linestyle='--', label='mt_under_crit')
            plt.axhline(y=1.06, color='g', linestyle='--', label='bt_over_crit')
            plt.axhline(y=1.047, color='g', linestyle='--', label='bt_over_prec')
            plt.axhline(y=0.866, color='g', linestyle='--', label='bt_under_prec')
            plt.axhline(y=0.92, color='g', linestyle='--', label='bt_under_crit')
            plt.grid(True, linestyle="--", alpha=0.5)

            # Ajusta limites autom�ticos
            plt.tight_layout()
            plt.ylim(inf_limite, super_limite)
            plt_path = os.path.join(self.data_dir, f"{file.stem}.png")
            plt.savefig(plt_path)
            #plt.savefig(plt_path, dpi=600, bbox_inches='tight', transparent=False)
            plt.show()

    def read_csv(filename):
        # Define a chunk size (number of rows)
        chunk_size = 10000

        for chunk in pd.read_csv(filename, chunksize=chunk_size):
            # Process each chunk individually
            print(chunk.head())


def load_config(circuito, config_path="smartRT.yml"):
    application_path = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(application_path, config_path), 'r') as file:
        config = yaml.load(file, Loader=yaml.BaseLoader)

    #config = config.get("databases", {}).get(circuito)
    config = config.get(circuito)
    if not config:
        raise ValueError(f"Configurações para '{circuito}' não foram encontradas.")
    return config

import pandas as pd
import matplotlib.pyplot as plt




if __name__ == "__main__":
    circuito = 'RMTQ1302'
    #circuito = 'RAVP1303'
    application_path = os.path.dirname(os.path.abspath(__file__))
    csv_file = os.path.join(application_path, fr'.\resultados\{circuito}\voltage_bus.csv')
    # read_csv(r".\resultados\RMTQ1302\voltage_bus.csv")

    # Leitura dos dados de configuração das pontos de medição e dos reguladores
    conf = load_config(circuito)
    pontos_med_faseA = conf['Pontos']['Node1']
    pontos_med_faseB = conf['Pontos']['Node2']
    pontos_med_faseC = conf['Pontos']['Node3']
    reguladores = conf['Reguladores']


    # inicializa a classe de analise dos resultados
    print("Inicialização da classe de análise gráfica...")
    results = Analisys(csv_file, "pesos.csv")

    # prefil de tensões
    print("Gráficos de pefil de tensão...")
    results.plot_perfil_tensao(os.path.join(application_path, fr'cenarios\{circuito}_TSEA'))

    # Tensões dos pontos de medição
    print("Gráficos de tensões nos pontos de medição...")
    results.plot_voltage_by_pesos(buses_phases=[pontos_med_faseA, pontos_med_faseB, pontos_med_faseC])

    # Taps - Vreg - Tensão do regulador
    print("Gráficos de Taps - Vreg - Tensão do regulador...")
    results.plot_taps()

    # Análise das condições das barras ao longo do dia
    print("Gráficos de análise de tensões de toddas as barras...")
    dados = results.polar_read_csv()
    results.plot_results(dados)

    exit()

    medicoes = ['mt4339274745933283mt02', 'mt4291205645697419mt02', 'mt4294449845693038mt02',
             'mt4283709245476469mt02', 'bt430501424549936mt02']

    medicoes = ['bt4274688645149945mt02', 'mt434452545570824mt02', 'bt4361929845347146mt02',
             'mt4283709245476469mt02', 'bt430501424549936mt02']

    medicoes = ['MT4288596845701482MT02', 'MT4294641145275648MT02', 'BT433404945857112MT02','BT4307607845467421MT02',
                'BT4274782645127345MT02']

    results.plot_voltage(buses_phases=[pontos_med_faseA, pontos_med_faseB, pontos_med_faseC])

