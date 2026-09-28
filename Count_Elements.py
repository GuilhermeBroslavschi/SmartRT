import py_dss_interface
import time
import os
import yaml
import pandas as pd
from pathlib import Path

application_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(application_path, "config_smartCAP.yml")
dss = py_dss_interface.DSS()

inicio = time.time()

with open(config_path, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)["data_smartCAP"]

utility = config["utility"]
feeders = config["feeder"]
months = config["month"]
type_days = config["type_day"]
num_patamares = config["num_patamares"]

for feeder in feeders:
    print(f"\n🚀 Processando o Feeder: {feeder}")
    substation = feeder[0:3] #feeder[1:4]
    dss_file = Path(f"C:/SmartRT/feeders/{utility}/{substation}/{feeder}/{type_days}_{months}_Master_{utility}_{substation}_{feeder}.dss")

    dss.text(f"compile [{dss_file}]")

    num_dg = 0
    kw_dg = 0
    dss.pvsystems.first()
    for _ in range(dss.pvsystems.count):
        dss.circuit.set_active_element(f"pvsystem[{dss.pvsystems.name}]")
        kw_pvsystem = dss.pvsystems.pmpp

        num_dg += 1
        kw_dg = kw_dg + kw_pvsystem
        dss.pvsystems.next()

    print(f"Quantidade de GDs: {num_dg}")
    print(f"Potência total: {kw_dg:.2f} kW")

    num_cap = 0
    kvar_cap = 0
    dss.capacitors.first()
    for _ in range(dss.capacitors.count):
        dss.circuit.set_active_element(f"capacitor[{dss.capacitors.name}]")
        kvar_capacitor = dss.capacitors.kvar

        num_cap += 1
        kvar_cap = kvar_cap + kvar_capacitor
        dss.capacitors.next()

    print(f"Quantidade de Capacitores: {num_cap}")
    print(f"Potência total: {kvar_cap:.2f} kVAr")

    num_trafo = 0
    kva_trafo = 0
    dss.transformers.first()
    for _ in range(dss.transformers.count):
        dss.circuit.set_active_element(f"transformer[{dss.transformers.name}]")
        trafo_name = dss.transformers.name
        kva_transformer = dss.transformers.kva

        # if trafo_name != 'reg_busa':
        if not trafo_name.lower().startswith("reg"):
            num_trafo += 1
            kva_trafo = kva_trafo + kva_transformer

        dss.transformers.next()

    print(f"Quantidade de Transformadores: {num_trafo}")
    print(f"Potência total: {kva_trafo:.2f} kVA")

    num_load = 0
    kw_load = 0
    dss.loads.first()
    for _ in range(dss.loads.count):
        dss.circuit.set_active_element(f"load[{dss.loads.name}]")
        kw_loads = dss.loads.kw

        num_load += 1
        kw_load = kw_load + kw_loads
        dss.loads.next()

    print(f"Quantidade de Cargas: {int(num_load / 2)}")
    print(f"Potência total: {kw_load:.2f} kW")

    file_exp = os.path.join(os.path.dirname(dss_file), f'{feeder}_EXP_Profile.CSV')
    dss.text(f"Export Profile Phases=All {file_exp}")
    dados = pd.read_csv(file_exp)
    max_distance = dados[' Distance2'].max()

    print(f"Comprimento do alimentador: {max_distance} km")
