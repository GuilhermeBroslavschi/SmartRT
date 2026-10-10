import os
import sys

import pandas as pd
import numpy as np

from flask import Flask, render_template, request, Response, url_for, redirect, jsonify
#from flask import flash

import io
import threading
from pathlib import Path
from datetime import datetime

# current = os.path.dirname(os.path.realpath(__file__))
# parent = os.path.dirname(current)
# sys.path.append(parent)

# execução da geração dos arquivos DSS pelo navegador.
from create_result_db import create_connection, load_config

pd.options.mode.copy_on_write = True
task_running = False  # Variável para evitar múltiplas execuções simultâneas -- control_bus

sys.path.append('../')
# Configuração do Flask
server = Flask(__name__)

ANOS = [2025, 2024]
MESES = list(range(1, 13))
MESES.insert(0, 'All')
DIAS = list(range(1, 29))
DIAS.insert(0, 'All')

LIMITE_INFERIOR_PU = 0.93
LIMITE_SUPERIOR_PU = 1.05

SOURCES = ['WIND', 'SOLAR']

conf = load_config()
engine = create_connection(conf)

#NUM_PATAMARES = load_config(db='num_patamares', config_path= 'config_smartCAP.yml', var='data_smartCAP' )
#step_slider = (int(NUM_PATAMARES) / 24)
hora_ref = 10

@server.route("/")
def dashboard():
    return render_template(
        "dashboard2.html",
        limite_inferior=LIMITE_INFERIOR_PU,
        limite_superior=LIMITE_SUPERIOR_PU,
        horario_referencia = hora_ref,
    )

@server.route("/get_date_options", methods=["POST"])
def get_date_options():
    ano = int(request.json.get("ano", datetime.now().year))
    return jsonify({"meses": MESES, "dias": DIAS, "sources": SOURCES})


@server.route("/api/circuitos")
def api_circuitos():
    try:
        query = f'''Select analise, cenario, cenario_id, controle_id, controle, sub, circuito from dbo.analise; '''
        circuitos = pd.read_sql_query(sql=query, con=engine)
        return circuitos.to_json(orient='records')

        #return jsonify([c.to_dict() for c in circuitos])
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@server.route("/api/capacitores")
def api_capacitores():
    try:
        cenario_id = request.args.get("cenario_id", type=int)
        controle_id = request.args.get("controle_id", type=int)
        circuito = request.args.get("circuito_id", type=str)

        if not cenario_id or not circuito:
            return jsonify({"erro": "Informe cenario_id e circuito"}), 400

        query = f'''Select nome, patamar, step, vmag_1, vmag_2, vmag_3, available_steps FROM dbo.capacitor 
            WHERE cenario_id={cenario_id} and controle_id={controle_id} 
            and circuito='{circuito}' 
            order by nome, patamar '''

        resultado = pd.read_sql_query(sql=query, con=engine)
        return resultado.to_dict(orient='list')

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@server.route("/api/perfil-tensao")
def api_perfil_tensao():
    try:
        cenario_id = request.args.get("cenario_id", type=int)
        controle_id = request.args.get("controle_id", type=int)
        circuito = request.args.get("circuito_id", type=str)
        hora = request.args.get("horas", type=int, default=0)
        tipo = request.args.get("tipo", type=int, default=0)   #  MT == 0 ou BT == 2

        if not cenario_id or not circuito:
            return jsonify({"erro": "Informe cenario_id e circuito"}), 400

        query = f'''Select patamar, node, tipo, v1, v2, distancia1, distancia2 FROM dbo.linha 
            WHERE v1 > 0.4 and tipo<={tipo} and cenario_id={cenario_id} and controle_id={controle_id} 
            and circuito='{circuito}' and hora={hora} 
            order by patamar '''
        resultado = pd.read_sql_query(sql=query, con=engine)
        return resultado.to_dict(orient='list')

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# @server.route("/api/perfil-tensao_old")
# def api_perfil_tensao_old():
#     try:
#         cenario_id = request.args.get("cenario_id", type=int)
#         circuito = request.args.get("circuito_id", type=str)
#         patamar = request.args.get("horas", type=int, default=0)
#         if not cenario_id or not circuito:
#             return jsonify({"erro": "Informe cenario_id e circuito"}), 400
#
#         query = f'''Select patamar, node, tipo, vln_pu, distancia FROM dbo.barra
#         WHERE vln_pu > 0.1 and tipo=1 and cenario_id ={cenario_id} and circuito='{circuito}' and patamar={patamar}
#         order by distancia, patamar '''
#         resultado = pd.read_sql_query(sql=query, con=engine)
#         return resultado.to_dict(orient='list')

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# ---------------------------------------------------------------
# Potencia ativa/reativa e perdas eletricas
# ---------------------------------------------------------------
@server.route("/api/potencia-perdas")
def api_potencia_perdas():
    try:
        cenario_id = request.args.get("cenario_id", type=int)
        circuito = request.args.get("circuito_id", type=str)
        controle_id = request.args.get("controle_id", type=int)
        if not cenario_id or not circuito:
            return jsonify({"erro": "Informe cenario_id e circuito"}), 400

        query = f'''Select patamar, hora, seg, p1, p2, p3, q1, q2, q3
                , ISNULL(p_losses, 0) as p_losses, ISNULL(q_losses, 0) as q_losses
                , ISNULL(p_losses_line, 0) as p_losses_line, ISNULL(q_losses_line, 0) as q_losses_line
                , p1/sqrt(POWER(p1,2)+POWER(q1,2)) as fp1
                , p2/sqrt(POWER(p2,2)+POWER(q2,2)) as fp2
                , p3/sqrt(POWER(p3,2)+POWER(q3,2)) as fp3
                , (p1+p2+p3) / sqrt(POWER((p1+p2+p3),2)+POWER((q1+q2+q3),2)) as fp_tri 
                from dbo.circuito 
                where cenario_id={cenario_id} and circuito='{circuito}' and controle_id={controle_id}  
                order by patamar '''

        resultado = pd.read_sql_query(sql=query, con=engine)

        return resultado.to_dict(orient='list')

        return jsonify({
            "horas": [r.patamar for r in resultado],
            "potencia_ativa_kw": [float(r.p1) for r in resultado],
            "potencia_reativa_kvar": [float(r.q1) for r in resultado],
            "perdas_kw": [float(r.perdas_kw) for r in resultado],
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# ---------------------------------------------------------------
# Análise comparativa - grafico radar
# ---------------------------------------------------------------
@server.route("/api/radar")
def api_radar():
    try:
        cenario_id = request.args.get("cenarios", type=int)
        #cenarios = request.args.get("cenarios", type=str)
        circuito = request.args.get("circuito_id", type=str)
        if not cenario_id or not circuito:
            return jsonify({"erro": "Informe cenario_id e circuito"}), 400

        #cenario_id = cenarios.split(',')[0]
        query = f'''WITH cte AS
                    (
                        SELECT
                            c.controle_id, c.nome, 
                            CASE
                                WHEN step <> LAG(step,1,0) OVER
                                (
                                    ORDER BY c.controle_id, nome, patamar
                                )
                                THEN 1
                            END AS stepChanged        
                        from capacitor c
                        join analise a on a.cenario_id = c.cenario_id 
                        where c.circuito='{circuito}' and c.cenario_id={cenario_id}
                    )
                    SELECT
                        controle_id,
                        COUNT(stepChanged) AS "stepChanged"                      
                    FROM cte
                    GROUP BY controle_id
                    ORDER BY controle_id
                '''

        resultado1 = pd.read_sql_query(sql=query, con=engine)
        resultado1['controle_id'] = resultado1['controle_id'].astype('int64')
        # normalizado no javascript
        #resultado1['stepChanged'] = resultado1['stepChanged'] / resultado1['stepChanged'].max() * 100

        query2 = f'''WITH dados AS (
                        SELECT 
                            a.controle,
                            SUM(SQRT(SQUARE(p_losses) + SQUARE(q_losses))) AS perdas
                        FROM circuito c
                        JOIN analise a 
                            ON a.cenario_id = c.cenario_id
                           AND a.controle_id = c.controle_id
                           AND a.circuito = c.circuito
                        where c.circuito='{circuito}' and c.cenario_id={cenario_id}                         
                        GROUP BY a.controle
                    )
                    SELECT 
                        d.controle,
                        a.controle_id,
                        d.perdas
                    FROM dados d
                    JOIN analise a
                        ON a.circuito='{circuito}' and a.cenario_id={cenario_id}     
                        AND a.controle = d.controle
                    ORDER BY d.perdas;
                '''

        resultado2 = pd.read_sql_query(sql=query2, con=engine)
        resultado2['controle_id'] = resultado2['controle_id'].astype('int64')

        query3 = f'''Select controle_id , count(*) barras from barra 
                    where tipo=2 and circuito='{circuito}' and cenario_id={cenario_id} 
                    and (vln_pu > 1.05 OR vln_pu < 0.93) 
                    group by controle_id
                '''
        resultado3 = pd.read_sql_query(sql=query3, con=engine)
        resultado3['controle_id'] = resultado3['controle_id'].astype('int64')

        #res = pd.merge(resultado1, resultado2, on='controle_id', how='outer')

        dfs = [resultado1, resultado2, resultado3]
        dfs = [df.set_index('controle_id') for df in dfs]
        # cant not run if index not unique
        res = pd.concat(dfs, join='outer', axis=1).fillna(0)

        return res.to_dict(orient='list')

        # return jsonify({
        #     "controle_id": [r.controle_id for r in resultado1],
        #     "stepChanged": [r.stepChanged for r in resultado1],
        #     "perdas": [float(r.perdas) for r in resultado2],
        # })

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# ---------------------------------------------------------------
# Fator de potência pela distância
# ---------------------------------------------------------------
# @server.route("/api/fp_distancia")
# def api_fp_distancia():
#     try:
#         cenario_id = request.args.get("cenario_id", type=int)
#         circuito = request.args.get("circuito_id", type=str)
#         controle_id = request.args.get("controle_id", type=int)
#         #hora = request.args.get("hora", type=int)
#         if not cenario_id or not circuito: # or not hora:
#             return jsonify({"erro": "Informe cenario_id, circuito e hora"}), 400
#
#         query = f'''SELECT hora, node, fp, distancia FROM dbo.barra
#                         WHERE cenario_id={cenario_id} AND circuito='{circuito}' AND controle_id={controle_id}
#                         ORDER BY distancia '''
#
#         # query = f'''SELECT hora, node, fp, distancia FROM dbo.barra
#         #         WHERE cenario_id={cenario_id} AND circuito='{circuito}' AND controle_id={controle_id} AND hora='{hora}'
#         #         ORDER BY distancia '''
#
#         resultado = pd.read_sql_query(sql=query, con=engine)
#
#         return resultado.to_dict(orient='list')
#
#     except Exception as e:
#         return jsonify({"erro": str(e)}), 500

@server.route("/api/fp_distancia")
def api_fp_distancia():
    try:
        cenario_id = request.args.get("cenario_id", type=int)
        circuito = request.args.get("circuito_id", type=str)
        controle_id = request.args.get("controle_id", type=int)
        hora = request.args.get("hora", type=int)

        if cenario_id is None or not circuito or controle_id is None or hora is None:
            return jsonify({"erro": "Informe cenario_id, circuito, controle_id e hora"}), 400

        query = f'''SELECT hora, node, fp, distancia FROM dbo.barra
                    WHERE cenario_id = {cenario_id} AND circuito = '{circuito}' AND controle_id = {controle_id} AND hora = {hora}
                    ORDER BY distancia'''

        resultado = pd.read_sql_query(sql=query, con=engine)

        return resultado.to_dict(orient='list')

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == '__main__':
    # server.run(host='0.0.0.0', use_reloader=False, debug=True, ssl_context=('cert.pem', 'key.pem'))
    server.run(host='0.0.0.0', use_reloader=False, debug=True)
    # Para rodar na linha de comando
    # C:\_BDGD2SQL\BDGD2SqlServer\venv\Scripts\activate.bat && python.exe C:\_BDGD2SQL\BDGD2SqlServer\ui\flask_app.py
