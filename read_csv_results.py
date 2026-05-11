import pandas as pd
import polars as pl
import time
import  os
import matplotlib
from pathlib import Path
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
        self.data_circuit = full_path.parts[1]
        self.pesos_data_path  = os.path.join(self.data_dir, self.pesos_data)

    def plot_pesos(self, dados):
        # graficos dos dados dos pesos.csv
        pass

    def plot_voltage(self, buses, node):
        # graficos dos dados
        # scan_csv doesn't load the file; it creates a plan
        df = pl.scan_csv(self.data_path)
        df = df.filter(pl.col("bus").is_in(buses) & (pl.col("nodes")==node) )
        df = df.select(["patamar", "bus", "vln_pu"])
        dados = df.collect().to_pandas()
        dados = dados.pivot(index='patamar', columns='bus', values='vln_pu')

        #print(dados)
        ax = dados.plot( y=buses, figsize=(10, 5))
        plt.title(f"BUS voltage")
        plt.ylabel(f"Voltage (p.u.) - {self.data_circuit}")
        plt.xlabel(f"Time steps")
        plt.grid(axis='y')
        #ax.xaxis.set_major_locator(ticker.MultipleLocator(690))
        plt_path = os.path.join(self.data_dir, "bus_medicoes_voltages.png")
        #plt.savefig(plt_path, dpi=300, bbox_inches='tight', transparent=False)
        plt.savefig(plt_path)
        plt.show()

    def plot_taps(self):
        df = pl.scan_csv(self.pesos_data_path)
        df = df.select(["patamar", "tap", "reg_voltage", "vreg"])
        dados = df.collect().to_pandas()


        fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(10, 8))

        dados["tap"].plot(ax=axes[0], title="TAP Change", color='blue')
        dados["vreg"].plot(ax=axes[1], title="Vref", color='red')
        dados["reg_voltage"].plot(ax=axes[2], title="Vreg", color='green')

        plt.xlabel(f"Time steps")
        plt.tight_layout()  # Prevents label overlapping
        plt.grid(axis='y')
        plt_path = os.path.join(self.data_dir, "tap_change.png")
        plt.savefig(plt_path)


        #ax = dados.plot(y="vreg", figsize=(10, 5))
        #plt.title(f"vreg")
        #plt.ylabel(f"vreg")
        #plt.xlabel(f"Time steps")
        #plt.grid(axis='y')
        # ax.xaxis.set_major_locator(ticker.MultipleLocator(690))
        #plt_path = os.path.join(self.data_dir, "vreg.png")
        # plt.savefig(plt_path, dpi=300, bbox_inches='tight', transparent=False)
        #plt.savefig(plt_path)



    def plot_rsults(self, dados):
        circuit = self.data_circuit
        # plt_path_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados", circuit)
        plt_path_base = self.data_dir
        pdf = dados.to_pandas()
        mt_df = pdf[['mt_undervolt_crit', 'mt_undervolt_prec', 'mt_overvolt_crit']].copy()
        bt_df = pdf[['bt_undervolt_prec', 'bt_undervolt_crit', 'bt_overvolt_prec', 'bt_overvolt_crit']].copy()

        counts_bt_under_prec_perc = bt_df['bt_undervolt_prec'] / pdf['cnt_bt_bus'][0] * 100
        counts_bt_under_crit_perc = bt_df['bt_undervolt_crit'] / pdf['cnt_bt_bus'][0] * 100
        counts_bt_over_prec_perc = bt_df['bt_overvolt_prec'] / pdf['cnt_bt_bus'][0] * 100
        counts_bt_over_crit_perc =  bt_df['bt_overvolt_crit'] / pdf['cnt_bt_bus'][0] * 100
        bt_df_perc = pd.DataFrame({'bt_undervoltage_prec': counts_bt_under_prec_perc,
                                   'bt_undervoltage_crit': counts_bt_under_crit_perc,
                                   'bt_overvoltage_prec': counts_bt_over_prec_perc,
                                   'bt_overvoltage_crit': counts_bt_over_crit_perc})

        counts_mt_under_prec_perc = mt_df['mt_undervolt_prec'] / pdf['cnt_mt_bus'][0] * 100
        counts_mt_under_crit_perc = mt_df['mt_undervolt_crit'] / pdf['cnt_mt_bus'][0] * 100
        counts_mt_over_crit_perc = mt_df['mt_overvolt_crit'] / pdf['cnt_mt_bus'][0] * 100
        mt_df_perc = pd.DataFrame({'mt_undervoltage_prec': counts_mt_under_prec_perc,
                                   'mt_undervoltage_crit': counts_mt_under_crit_perc,
                                   'mt_overvoltage_crit': counts_mt_over_crit_perc})
        espacamento = 690
        if not bt_df.empty :
            ax = bt_df.plot(kind='bar', stacked=True)
            plt.title(f"BUS Violation : {circuit}")
            plt.ylabel(f"Number")
            plt.xlabel(f"Time steps")
            plt.grid(axis='y')
            ax.xaxis.set_major_locator(ticker.MultipleLocator(espacamento))
            plt_path = os.path.join(plt_path_base, "bt_voltages.png")
            plt.savefig(plt_path, dpi=600, bbox_inches='tight', transparent=False)
            plt.show(block=False)

            # grafico de porcentagem
            ax = bt_df_perc.plot(kind='bar', stacked=True)
            plt.title(f"BUS Violation : {circuit}")
            plt.ylabel(f"Number (%)")
            plt.xlabel(f"Time steps")
            plt.grid(axis='y')
            ax.xaxis.set_major_locator(ticker.MultipleLocator(espacamento))
            plt_path = os.path.join(plt_path_base, "bt_voltages_perc.png")
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
        # scan_csv doesn't load the file; it creates a plan
        lazy_df = pl.scan_csv(self.data_path)

        filtered_df = (
            lazy_df
            .group_by("patamar")
            .agg(
                ((pl.col("kv_base") > 1000) & (pl.col("vln_pu") > 1.05)).sum().alias("mt_overvolt_crit"),
                ((pl.col("kv_base") > 1000) & ((pl.col("vln_pu") >= 0.90) & (pl.col("vln_pu") < 0.93))).sum().alias("mt_undervolt_prec"),
                ((pl.col("kv_base") > 1000) & (pl.col("vln_pu") < 0.90)).sum().alias("mt_undervolt_crit"),

                ((pl.col("kv_base") < 1000) & (pl.col("vln") < 110)).sum().alias("bt_undervolt_crit"),
                ((pl.col("kv_base") < 1000) & ((pl.col("vln") >= 110) & (pl.col("vln") < 117))).sum().alias("bt_undervolt_prec"),
                ((pl.col("kv_base") < 1000) & ((pl.col("vln") >= 133) & (pl.col("vln") < 135))).sum().alias("bt_overvolt_prec"),
                ((pl.col("kv_base") < 1000) & (pl.col("vln") >= 135) ).sum().alias("bt_overvolt_crit"),

                (pl.col("kv_base") < 1000).sum().alias("cnt_bt_bus"),
                (pl.col("kv_base") > 1000).sum().alias("cnt_mt_bus"),

                 )
            .sort(pl.col("patamar").cast(pl.UInt16), descending=False)

        )

        results  = filtered_df.collect(engine="streaming")
        print(f"Result:   {results}")
        print(f"Processo concluído em {time.time() - proc_time_ini}")
        return results


    def read_csv(filename):
        # Define a chunk size (number of rows)
        chunk_size = 10000

        for chunk in pd.read_csv(filename, chunksize=chunk_size):
            # Process each chunk individually
            print(chunk.head())

if __name__ == "__main__":
    # read_csv(r".\resultados\RMTQ1302\voltage_bus.csv")

    results = Analisys(r".\resultados\RMTQ1302\sem_setup_dinamido\voltage_bus.csv", "pesos.csv")

    results.plot_taps()


    medicoes = ['mt4339274745933283mt02', 'mt4291205645697419mt02', 'mt4294449845693038mt02',
             'mt4283709245476469mt02', 'bt430501424549936mt02']
    results.plot_voltage(buses=medicoes, node=1)

    exit()
    dados = results.polar_read_csv()
    results.plot_rsults(dados)
