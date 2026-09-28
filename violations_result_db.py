import yaml
import os
import time
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from pathlib import Path

def load_config(db = 'resultsDB', config_path="config_database.yml", var = None):

    application_path = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(application_path, config_path), 'r') as file:
        config = yaml.load(file, Loader=yaml.BaseLoader)

    if config_path == "config_database.yml":
        config = config.get("databases", {}).get(db)
    else:
        config = config.get(var, {}).get(db)

    if not config:
        raise ValueError(f"Configurações para '{db}' não foram encontradas.")
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

def plotar_voltage_per(df_violations, titulo, tipo, cenario_nome, controle_nome, caminho_arquivo):

    caminho_arquivo.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.bar(
        df_violations.index,
        df_violations["subtensao"],
        label="Subtensão"
    )

    ax.bar(
        df_violations.index,
        df_violations["sobretensao"],
        bottom=df_violations["subtensao"],
        label="Sobretensão"
    )

    ax.set_xlabel("Hora")
    ax.set_ylabel("Barras violadas (%)")

    ax.set_title(
        f"{titulo} {tipo}: "
        f"{cenario_nome} - {controle_nome}"
    )

    ax.legend(title=None)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.set_xticks(df_violations.index)
    ax.tick_params(axis="x", rotation=0)
    ax.margins(x=0)

    plt.savefig(caminho_arquivo, dpi=300, bbox_inches="tight")
    plt.close()

def feeder_results(cenarios, controles):
    for cenario in cenarios:

        cenario_id = cenario.split(",")[0]
        cenario_nome = cenario.split(",")[1]

        print("=" * 60)
        print(f"Cenário {cenario_nome}")

        n = 0
        total_barras = 0
        for controle in controles:
            data_violations = list()

            controle_id = controle.split(",")[0]
            controle_nome = controle.split(",")[1]

            query_bus_mt = f"""
                            SELECT
                                [circuito],                        
                                [hora],
                                [bus],
                                [vln_pu],
                                [tipo]
                            FROM [resultsDB].[dbo].[barra]
                            WHERE [cenario_id] = {cenario_id}
                              AND [controle_id] = {controle_id}
                              AND [tipo] = 2;                      
                            """

            query_losses = f"""
                            SELECT                            
                                [p_losses]
                            FROM[resultsDB].[dbo].[circuito]
                            WHERE [cenario_id] = {cenario_id}
                              AND [controle_id] = {controle_id};                                                
                            """

            df_violation = pd.read_sql(query_bus_mt, engine)
            df_losses = pd.read_sql(query_losses, engine)

            if n == 0:
                total_barras = df_violation["bus"].nunique()
                n += 1
                print(f"Total de barras de MT: {total_barras}")

            if df_violation.empty:
                print(f"❌ Cenário para o controle escolhido não foi encontrado: {cenario}-{controle}")
                continue

            print(f"Controle {controle_nome}")

            total_perdas = df_losses["p_losses"].sum()
            print(f"Perdas totais: {total_perdas:.2f} kWh")

            for circuito, df_circuito in df_violation.groupby("circuito"):
                fig_voltage_bus_per = Path(f"C:/SmartRT/resultados/{circuito}/{cenario_nome}/{circuito}_{cenario_nome}_{controle_nome}_MT_bus_per.png")

            for hora, df_hora in df_violation.groupby("hora"):

                subtensao = df_hora["vln_pu"] < 0.93
                sobretensao = df_hora["vln_pu"] > 1.05

                barras_subtensao = df_hora.loc[subtensao, "bus"].nunique()
                barras_sobretensao = df_hora.loc[sobretensao, "bus"].nunique()

                if total_barras > 0:
                    porcentagem_subtensao = (barras_subtensao / total_barras) * 100
                    porcentagem_sobretensao = (barras_sobretensao / total_barras) * 100

                else:
                    porcentagem_subtensao = 0
                    porcentagem_sobretensao = 0

                data_violations.append({
                    "hora": hora,
                    "subtensao": porcentagem_subtensao,
                    "sobretensao": porcentagem_sobretensao
                })

                # print(f"\nHora: {hora}")
                # print(f"Subtensão: {barras_subtensao} barras "
                #       f"({porcentagem_subtensao:.2f}%)")
                # print(f"Sobretensão: {barras_sobretensao} barras "
                #       f"({porcentagem_sobretensao:.2f}%)")

            df_violations = pd.DataFrame(data_violations)
            df_violations = df_violations.set_index("hora")

            plotar_voltage_per(df_violations, "BARRAS", "MT Violadas", cenario_nome, controle_nome, fig_voltage_bus_per)
            print("Gráfico das tensões violadas executado")
        print("=" * 60)

def to_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

if __name__ == '__main__':
    conf = load_config('resultsDB')
    engine = create_connection(conf)

    application_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(application_path, "config_smartCAP.yml")

    inicio = time.time()

    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)["data_smartCAP"]

    cenarios = to_list(config.get("cenario", []))
    controles = to_list(config.get("controle", []))

    feeder_results(cenarios, controles)

    fim = time.time()
    tempo_total = fim - inicio

    horas = int(tempo_total // 3600)
    minutos = int((tempo_total % 3600) // 60)
    segundos = int(tempo_total % 60)

    print(f"Tempo total de execução: {horas:02d}h{minutos:02d}min{segundos:02d}seg")
    print("✅ Execução Completa")