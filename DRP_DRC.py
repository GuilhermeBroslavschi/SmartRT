import os
from dataclasses import dataclass, asdict
from typing import Optional, List
import matplotlib
import pandas as pd
import seaborn as sns
import yaml

matplotlib.use('TKAgg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import json
from sqlalchemy import create_engine


@dataclass
class DRP:
    load: str = ""
    tipo: str = ""
    num_leituras: int = 0
    value: float = 0
    bus: Optional[str] = ""
    drp_l: float = 0.03         # limites para os indicadores individuais DRP
    tusd_bt: float = 0.45667    # R$/kWh
    tusd_mt: float = 4.95
    demanda: float = 0.1
    drp_comp: float = 0.0

    def __post_init__(self):
        k = 0
        tusd = self.tusd_bt
        if self.tipo == 'mt':
            tusd = self.tusd_mt
        if self.value > self.drp_l:
            k = 3
        self.drp_comp = ((self.value - self.drp_l) / 100) * k * tusd * self.demanda


@dataclass
class DRC:
    load: str = ""
    tipo: str = ""
    num_leituras: int = 0
    value: float = 0
    bus: Optional[str] = ""
    drc_l: float = 0.005  # limites para os indicadores individuais DRC
    tusd_bt: float = 0.45667
    tusd_mt: float = 4.95
    demanda: float = 0.1    # kWh
    drc_comp: float = 0.0

    def __post_init__(self):
        k = 0
        tusd = self.tusd_bt
        if self.tipo == 'mt':
            tusd = self.tusd_mt
        if self.value > self.drc_l:
            if self.tipo == 'bt':
                k = 7
            else:
                k = 3
        self.drc_comp = ((self.value - self.drc_l) / 100) * k * tusd * self.demanda


@dataclass
class Indicadores:
    drc: List[DRC]
    drp: List[DRP]
    data_ref: str               # mês de referencia do indicador
    circuito: str
    nl: int                     # total de unidades consumidoras objeto de medição;
    nc: int = 0                 # total de unidades consumidoras com indicador individual DRC diferente de 0 (zero);
    icc: Optional[float] = 0    # Índice de Unidades Consumidoras com Tensão Crítica
    drp_e: float = 0            # Duração Relativa da Transgressão de Tensão Precária Equivalente
    drc_e: float = 0            # Duração Relativa da Transgressão de Tensão Crítica Equivalente
    comp_total: float = 0       # Somatória das compensões - comp(DRC) + comp(DRP)

    def __post_init__(self):
        self.nc = len(self.drc)
        self.icc = round((self.nc / self.nl) * 100, 3)
        self.drp_e = round(sum([x.value / self.nl for x in self.drp]), 3)
        self.drc_e = round(sum([x.value / self.nl for x in self.drc]), 3)
        self.comp_total = round(sum([x.drp_comp for x in self.drp]) + sum([x.drc_comp for x in self.drc]),2)


def sum_drc_drp_comp(drc_list: List[DRC], drp_list: List[DRP], circuito, json_file=None) -> dict:
    """
    Retorna um dicionário com a soma de `drc_comp` e `drp_comp` por load.

    Regras:
    - Se existir DRC e DRP para o mesmo `load`, soma `drc_comp + drp_comp`.
    - Se existir apenas DRC, retorna apenas `drc_comp`.
    - Se existir apenas DRP, retorna apenas `drp_comp`.

    Parâmetros:
    - drc_list: lista de instâncias DRC
    - drp_list: lista de instâncias DRP

    Retorno:
    - dict onde chave é o nome do load e valor é a soma dos comps (float)
    """
    if json_file:
        # Open the file and load its content
        with open(json_file) as f:
            data = json.load(f)
        drp = pd.json_normalize(data, record_path=['drp'])
        drc = pd.json_normalize(data, record_path=['drc'])
        drp_list = [DRP(**row) for row in drp.to_dict('records')]
        drc_list = [DRC(**row) for row in drc.to_dict('records')]

    application_path = os.path.dirname(os.path.abspath(__file__))
    plt_path_base = os.path.join(application_path, fr'resultados\{circuito}')
    #plt_path_base = os.path.join(rf"C:\pastaD\TSEA\Analises\base_case", circuito)
    result = {}

    # Somar os valores de drc_comp
    for drc in drc_list:
        if not drc or not getattr(drc, 'load', None):
            continue
        key = drc.load
        result[key] = result.get(key, 0.0) + (drc.drc_comp or 0.0)

    # Somar os valores de drp_comp
    for drp in drp_list:
        if not drp or not getattr(drp, 'load', None):
            continue
        key = drp.load
        result[key] = result.get(key, 0.0) + (drp.drp_comp or 0.0)
    dados_comp = pd.DataFrame.from_dict(result, orient='index', columns=['comp'])
    dados_comp = dados_comp.reset_index(names='load')

    for p in ['bt', 'mt']:

        dados_comp = dados_comp.loc[dados_comp['load'].str.startswith(p)]
        if dados_comp.empty:
            print(f"Sem dados de violação de tensão para a rede {p}.")
            continue

        desc = dados_comp.describe()
        # Add a row for the sum
        desc.loc['sum'] = dados_comp['comp'].sum()
        # Save to Excel
        desc.to_excel(os.path.join(plt_path_base, f"{p}_summary.xlsx"))
        print(desc)
        #df = sns.load_dataset("penguins")

        # 2. Criar o histograma com curva de densidade (KDE)
        plt.figure(figsize=(10, 6))
        #fig, axes = plt.subplots(1, 2)
        ax = sns.histplot(data=dados_comp,  x="comp", bins=10)

        #sns.boxplot(data=dados_comp, x="load", y="comp", showmeans=True, ax=axes[1])
        #plt.show()
        # 1. Create the boxplot (base)
        #ax = sns.boxplot(data=dados_comp, y="load", color="white")
        # 2. Overlay the stripplot
        #sns.stripplot(data=dados_comp,  y="load", hue="comp", jitter=True, alpha=0.5)
        #sns.histplot(data=df, x="flipper_length_mm")
        #sns.kdeplot(data=dados_comp, fill=True, color='red')
        #sns.displot(data=dados_comp, x="load", col="comp", kde=True)

        plt.title(f'Compensações: {circuito}: {p} - Distribuição Estatística')
        plt.xlabel('Compensação Média (R$/Mês)')
        plt.ylabel('Frequência')
        plt_path = os.path.join(plt_path_base, f"indicadores_tensao_{p}_histplot.png")
        plt.savefig(plt_path, dpi=300, bbox_inches='tight', transparent=False)
        plt.show()

        ax = sns.stripplot(data=dados_comp, x="load", y="comp")
        plt.title(f'Compensações: {circuito}: {p} - Distribuição Estatística')
        plt.ylabel('Compensação Média (R$/Mês)')
        x_tc = (len(dados_comp['load']) // 20)
        if x_tc < 5:
            x_tc = 1
        #print(x_tc)
        ax.xaxis.set_major_locator(ticker.MultipleLocator(x_tc))

        # 2. Define the maximum character limit
        max_len = 5
        # 3. Truncate labels and reapply
        labels = [label.get_text()[:max_len] + ('...' if len(label.get_text()) > max_len else '')
                  for label in ax.get_xticklabels()]
        ax.set_xticklabels(labels)
        plt.xticks(fontsize=6, rotation=45)
        plt_path = os.path.join(plt_path_base, f"indicadores_tensao_{p}_stripplot.png")
        plt.savefig(plt_path, dpi=300, bbox_inches='tight', transparent=False)
        plt.show()

        fig, ax = plt.subplots()
        sns.boxplot(data=dados_comp, ax=ax)
        # Place the summary text in the plot area
        desc = dados_comp['comp'].describe()
        desc.loc['Total'] = dados_comp['comp'].sum()
        stats_text = desc.to_string()
        plt.figtext(0.68, 0.6, stats_text, family='monospace', fontsize=7)
        plt.title(f'Compensações: {circuito}: {p} - Boxplot')
        plt_path = os.path.join(plt_path_base, f"indicadores_tensao_{p}_boxplot.png")
        plt.savefig(plt_path, dpi=300, bbox_inches='tight', transparent=False)
        plt.show()

    return result

def load_config(circuito, config_path="config_database.yml"):
    application_path = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(application_path, config_path), 'r') as file:
        config = yaml.load(file, Loader=yaml.BaseLoader)

    config = config.get("databases", {}).get(circuito)

    if not config:
        raise ValueError(f"Configurações para '{circuito}' não foram encontradas.")
    return config

def create_connection(config_bdgd):
    """Função para criar uma conexão com o banco de dados SQL Server"""

    engine = create_engine(f"mssql+pyodbc://"
                           f"{config_bdgd['username']}:"
                           f"{config_bdgd['password']}@"
                           f"{config_bdgd['server']}/"
                           f"{config_bdgd['database']}?"
                           f"driver=ODBC+Driver+17+for+SQL+Server",
                           fast_executemany=True, pool_pre_ping=True)

    return engine


def get_demand_from_load(circuit, type, database):
    config = load_config(database)
    engine = create_connection(config)
    query = f'''  Select  cod_id , pac as bus, (COALESCE(ENE_01, 0) + COALESCE(ENE_02, 0) + COALESCE(ENE_03, 0) + COALESCE(ENE_04, 0) + 
    COALESCE(ENE_05, 0) + COALESCE(ENE_06, 0) + COALESCE(ENE_07, 0) + COALESCE(ENE_08, 0) + COALESCE(ENE_09, 0) + 
    COALESCE(ENE_10, 0) + COALESCE(ENE_11, 0) + COALESCE(ENE_12, 0)) / 
        (CASE WHEN ENE_01 <> 0 THEN 1 ELSE 0 END + CASE WHEN ENE_02 <> 0 THEN 1 ELSE 0 END + 
         CASE WHEN ENE_03 <> 0 THEN 1 ELSE 0 END + CASE WHEN ENE_04 <> 0 THEN 1 ELSE 0 END + 
         CASE WHEN ENE_05 <> 0 THEN 1 ELSE 0 END + CASE WHEN ENE_06 <> 0 THEN 1 ELSE 0 END + 
         CASE WHEN ENE_07 <> 0 THEN 1 ELSE 0 END + CASE WHEN ENE_08 <> 0 THEN 1 ELSE 0 END + 
         CASE WHEN ENE_09 <> 0 THEN 1 ELSE 0 END + CASE WHEN ENE_10 <> 0 THEN 1 ELSE 0 END + 
         CASE WHEN ENE_11 <> 0 THEN 1 ELSE 0 END + CASE WHEN ENE_12 <> 0 THEN 1 ELSE 0 END) as avg_demand
         FROM sde.{type} where  CTMT = '{circuit}'  and SIT_ATIV='AT' and
         (ENE_01 <> 0 OR ENE_02 <> 0 OR ENE_03 <> 0 OR ENE_04 <> 0 OR ENE_05 <> 0 OR ENE_06 <> 0 OR
          ENE_07 <> 0 OR ENE_08 <> 0 OR ENE_09 <> 0 OR ENE_10 <> 0 OR ENE_11 <> 0 OR ENE_12 <> 0 
         ) ;  '''

    with engine.connect() as conn:
        demand = pd.read_sql_query(query, conn)
    return demand

def get_load_buses(dss):
    dss.Loads.First()
    load_buses = {}

    while True:
        load_name = dss.Loads.Name()
        load_bus = dss.Loads.Bus()
        load_buses[load_name] = load_bus

        if dss.Loads.Next() == 0:
            break
    return load_buses


def demanda_load(circuito):
    print("Obtendo demandas das cargas...")
    database = '391_2024'
    demand_load_bt = get_demand_from_load(circuito, 'UCBT', database)
    demand_load_bt['cod_id'] = "bt_" + demand_load_bt['cod_id'] + "_m1"
    demand_load_mt = get_demand_from_load(circuito, 'UCMT', database)
    demand_load_mt['cod_id'] = "mt_" + demand_load_mt['cod_id'] + "_m1"
    all_demand_load = pd.concat([demand_load_bt,demand_load_mt])
    all_demand_load['bus'] = all_demand_load['bus'].str.lower()
    return all_demand_load


def indic_DRP_DRC(circuito, dados_drp_drc, demand_load):
    """
    # Indicadores individuais de tensão em regime permanente
    nlp = maior valor entre as fases do número de leituras situadas na faixa precária; e
    nlc = maior valor entre as fases do número de leituras situadas na faixa crítica.
    :return:
    """

    indic_data_ref = '20260301'
    nun_leituras = 17280    # int(1008 / 7)  # amostras 10 min, 7 dias = 168 horas
    drc_list = []
    drp_list = []

    print(f"Calculand")
    for row in dados_drp_drc.itertuples():
        load = row.cod_id
        bt_nlp = row.bt_undervolt_prec + row.bt_overvolt_prec
        bt_nlc = row.bt_undervolt_crit + row.bt_overvolt_crit

        mt_nlp = row.mt_undervolt_prec
        mt_nlc = row.mt_undervolt_crit + row.mt_overvolt_crit
        demanda = demand_load.loc[demand_load['cod_id'] == load, ['avg_demand']].values[0][0]

        if bt_nlp > 0:
            drp_list.append(DRP(load=load, tipo='bt', demanda=demanda, num_leituras=nun_leituras, value=(bt_nlp / nun_leituras) * 100))

        if bt_nlc > 0:
            drc_list.append(DRC(load=load, tipo='bt', demanda=demanda, num_leituras=nun_leituras, value=(bt_nlc / nun_leituras) * 100))

        if mt_nlp > 0:
            drp_list.append(DRP(load=load, tipo='mt', demanda=demanda, num_leituras=nun_leituras, value=(mt_nlp / nun_leituras) * 100))

        if mt_nlc > 0:
            drc_list.append(DRC(load=load, tipo='mt', demanda=demanda, num_leituras=nun_leituras, value=(mt_nlc / nun_leituras) * 100))

    indicadores = Indicadores(
        drc=drc_list,
        drp=drp_list,
        data_ref=indic_data_ref,
        circuito=circuito,
        #nl=agg.index.get_level_values(0).nunique()
        nl=dados_drp_drc.shape[0]
    )
    p_dict = asdict(indicadores)

    application_path = os.path.dirname(os.path.abspath(__file__))
    path_file = os.path.join(application_path, fr'resultados\{circuito}\{circuito}_indicadores.json')
    # write json
    with open(path_file, 'w') as f:
        # Convert dataclass to a dictionary

        # Serialize the dictionary to a JSON string
        indi_json = json.dumps(p_dict, indent=4)
        f.write(indi_json)

    sum_drc_drp_comp(drc_list, drp_list, circuito)

