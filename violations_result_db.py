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

    # ax.set_ylim(0, 80)  # TODO - USAR QUANDO NECESSÁRIO

    plt.savefig(caminho_arquivo, dpi=300, bbox_inches="tight")
    plt.close()

def feeder_results(cenarios, controles):
    m = 0
    data_losses = list()
    data_fp = list()
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

            query_fp = f"""
                        SELECT
                            soma_p1,
                            soma_p2,
                            soma_p3,
                            soma_q1,
                            soma_q2,
                            soma_q3,

                            -- Potência total
                            soma_p1 + soma_p2 + soma_p3 AS soma_p_total,
                            soma_q1 + soma_q2 + soma_q3 AS soma_q_total,
                
                            -- Fator de potência por fase
                            soma_p1 / SQRT(POWER(soma_p1, 2) + POWER(soma_q1, 2)) AS fp1,
                            soma_p2 / SQRT(POWER(soma_p2, 2) + POWER(soma_q2, 2)) AS fp2,
                            soma_p3 / SQRT(POWER(soma_p3, 2) + POWER(soma_q3, 2)) AS fp3,
                
                            -- Fator de potência trifásico
                            (soma_p1 + soma_p2 + soma_p3) /
                            SQRT(POWER(soma_p1 + soma_p2 + soma_p3, 2) + POWER(soma_q1 + soma_q2 + soma_q3, 2)) AS fp_trifasico,
                
                            -- Tipo de FP por fase 
                            CASE
                                WHEN soma_q1 > 0 THEN 'Indutivo'
                                WHEN soma_q1 < 0 THEN 'Capacitivo'
                                ELSE 'Unitário'
                            END AS tipo_fp1,
                
                            CASE
                                WHEN soma_q2 > 0 THEN 'Indutivo'
                                WHEN soma_q2 < 0 THEN 'Capacitivo'
                                ELSE 'Unitário'
                            END AS tipo_fp2,
                
                            CASE
                                WHEN soma_q3 > 0 THEN 'Indutivo'
                                WHEN soma_q3 < 0 THEN 'Capacitivo'
                                ELSE 'Unitário'
                            END AS tipo_fp3,

                            -- Tipo de FP trifásico
                            CASE
                                WHEN(soma_q1 + soma_q2 + soma_q3) > 0 THEN 'Indutivo'
                                WHEN(soma_q1 + soma_q2 + soma_q3) < 0 THEN 'Capacitivo'
                                ELSE 'Unitário'
                            END AS tipo_fp_trifasico

                        FROM(
                            SELECT
                                SUM([p1]) AS soma_p1,
                                SUM([p2]) AS soma_p2,
                                SUM([p3]) AS soma_p3,
                                SUM([q1]) AS soma_q1,
                                SUM([q2]) AS soma_q2,
                                SUM([q3]) AS soma_q3
                            FROM[resultsDB].[dbo].[circuito]
                            WHERE[cenario_id] = {cenario_id}
                            AND[controle_id] = {controle_id}
                        ) AS dados;
                        """

            df_violation = pd.read_sql(query_bus_mt, engine)
            df_losses = pd.read_sql(query_losses, engine)
            df_fp = pd.read_sql(query_fp, engine)

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

            data_losses.append({
                "cenario": cenario_nome,
                "controle": controle_nome,
                "Perdas (kWh)": total_perdas
            })

            fp1 = df_fp["fp1"].iloc[0]
            fp2 = df_fp["fp2"].iloc[0]
            fp3 = df_fp["fp3"].iloc[0]
            fp_trifasico = df_fp["fp_trifasico"].iloc[0]
            tipo_fp1 = df_fp["tipo_fp1"].iloc[0]
            tipo_fp2 = df_fp["tipo_fp2"].iloc[0]
            tipo_fp3 = df_fp["tipo_fp3"].iloc[0]
            tipo_fp_trifasico = df_fp["tipo_fp_trifasico"].iloc[0]
            print(f"FP trifásico: {fp_trifasico:.4f} {tipo_fp_trifasico}")

            data_fp.append({
                "cenario": cenario_nome,
                "controle": controle_nome,
                "fp1": fp1,
                "fp2": fp2,
                "fp3": fp3,
                "fp_trifasico": fp_trifasico,
                "tipo_fp1": tipo_fp1,
                "tipo_fp2": tipo_fp2,
                "tipo_fp3": tipo_fp3,
                "tipo_fp_trifasico": tipo_fp_trifasico
            })

            for circuito, df_circuito in df_violation.groupby("circuito"):
                fig_voltage_bus_per = Path(f"C:/SmartRT/resultados/{circuito}/{cenario_nome}/{circuito}_{cenario_nome}_{controle_nome}_MT_bus_per.png")
                if m == 0:
                    losses_path = Path(f"C:/SmartRT/resultados/{circuito}/{circuito}_losses_kWh.csv")
                    fp_path = Path(f"C:/SmartRT/resultados/{circuito}/{circuito}_fp.csv")
                    m += 1

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

    df_data_losses = pd.DataFrame(data_losses)
    df_data_losses.to_csv(losses_path, index=False)

    df_data_fp = pd.DataFrame(data_fp)
    df_data_fp.to_csv(fp_path, index=False)

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