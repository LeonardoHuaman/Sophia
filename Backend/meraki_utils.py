import os
import json
import ast
import re
import time
import requests
import meraki
import xml.etree.ElementTree as ET
from tqdm import tqdm
from dotenv import load_dotenv
from langchain.tools import Tool
# from frame_analyzer import analyze_image_to_json  # Función para analizar imágenes

# Deshabilitar advertencias HTTPS no verificadas (solo para desarrollo)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Cargar variables de entorno desde .env
load_dotenv()
MERAKI_KEY = os.getenv("MERAKI_KEY")
if not MERAKI_KEY:
    raise ValueError("❌ ERROR: La clave MERAKI_KEY no está definida en el archivo .env")

# Configuración global para Meraki
NETWORK_ID = "L_3698581193978021054"
SAVE_PATH = "imagenes_camaras"  # Carpeta donde se guardarán las imágenes

# Inicializar el cliente Meraki
dashboard = meraki.DashboardAPI(MERAKI_KEY, suppress_logging=True)


def extract_value(input_data, key):
    """
    Intenta convertir input_data (si es un string) a un diccionario y extraer el valor asociado a 'key'.
    Si no se puede, devuelve input_data tal cual.
    """
    if isinstance(input_data, str):
        try:
            parsed_json = json.loads(input_data)
            if isinstance(parsed_json, dict) and key in parsed_json:
                return parsed_json[key]
        except json.JSONDecodeError:
            try:
                parsed_literal = ast.literal_eval(input_data)
                if isinstance(parsed_literal, dict) and key in parsed_literal:
                    return parsed_literal[key]
            except Exception:
                # Si falla, se retorna el input original sin mostrar error
                return input_data
    elif isinstance(input_data, dict):
        if key in input_data:
            return input_data[key]
    return input_data


# ==============================================================================
# FUNCIONES BÁSICAS DE REPORTES PARA MERAKI (versión actual sin guardado en JSON)
# ==============================================================================

def list_organizations(*args, **kwargs):
    """Devuelve una lista de organizaciones en la cuenta de Meraki."""
    try:
        return dashboard.organizations.getOrganizations()
    except Exception as e:
        return {"error": f"❌ Error en list_organizations(): {e}"}


def list_networks(org_id, *args, **kwargs):
    """Devuelve el listado de redes de una organización. Requiere org_id."""
    org_id = extract_value(org_id, 'org_id')
    org_id = str(org_id).strip()
    if not org_id or org_id.lower() == "none":
        return {"error": f"❌ Error: org_id tiene un formato incorrecto: {org_id}"}
    try:
        return dashboard.organizations.getOrganizationNetworks(org_id)
    except Exception as e:
        return {"error": f"❌ Error en list_networks({org_id}): {e}"}


def list_devices(network_id, *args, **kwargs):
    """Devuelve la lista de dispositivos en una red. Requiere network_id."""
    network_id = extract_value(network_id, 'network_id')
    network_id = str(network_id).strip()
    if not network_id:
        return {"error": "❌ Error: Se necesita un network_id válido para listar dispositivos."}
    try:
        devices = dashboard.networks.getNetworkDevices(network_id)
        # Limpiar datos irrelevantes
        for device in devices:
            for key in ["lat", "lng", "address", "tags", "url", "networkId", "details"]:
                device.pop(key, None)
        return devices
    except Exception as e:
        return {"error": f"❌ Error en list_devices({network_id}): {e}"}


def list_clients(network_id, *args, **kwargs):
    """Devuelve la lista de clientes conectados a una red. Requiere network_id."""
    network_id = extract_value(network_id, 'network_id')
    network_id = str(network_id).strip()
    if not network_id:
        return {"error": "❌ Error: Se necesita un network_id válido para listar clientes."}
    try:
        return dashboard.networks.getNetworkClients(network_id, total_pages="all")
    except Exception as e:
        return {"error": f"❌ Error en list_clients({network_id}): {e}"}


def get_subscription_end_date(org_id, *args, **kwargs):
    """Devuelve la fecha de expiración de la suscripción de una organización. Requiere org_id."""
    org_id = extract_value(org_id, 'org_id')
    org_id = str(org_id).strip()
    if not org_id:
        return {"error": "❌ Error: Se necesita un org_id válido para obtener la fecha de suscripción."}
    try:
        data = dashboard.organizations.getOrganizationLicensesOverview(org_id)
        return {"expirationDate": data.get("expirationDate", "Desconocido")}
    except Exception as e:
        return {"error": f"❌ Error en get_subscription_end_date({org_id}): {e}"}


def get_network_status(network_id, *args, **kwargs):
    """
    Genera un reporte resumido del estado de la red basado en la cantidad de dispositivos y clientes.
    Requiere network_id.
    """
    devices = list_devices(network_id)
    clients = list_clients(network_id)
    try:
        report = {
            "total_devices": len(devices) if isinstance(devices, list) else "N/A",
            "total_clients": len(clients) if isinstance(clients, list) else "N/A"
        }
        return report
    except Exception as e:
        return {"error": f"❌ Error en get_network_status({network_id}): {e}"}


def list_firewall_rules(network_id):
    """Listar las reglas de firewall configuradas en una red."""
    try:
        data = dashboard.appliance.getNetworkApplianceFirewallL3FirewallRules(network_id)
        if not data.get('rules') or len(data.get('rules', [])) == 1:
            print("⚠ Solo se encontró la regla por defecto o no hay reglas personalizadas.")
        return data
    except Exception as e:
        return {"error": f"❌ Error en list_firewall_rules({network_id}): {e}"}


def list_wireless_channels(network_id):
    """Listar canales inalámbricos ordenados por saturación."""
    try:
        devices = dashboard.networks.getNetworkDevices(network_id)
        wireless_devices = [device for device in devices if device.get('model', '').startswith('MR')]
        if not wireless_devices:
            print("⚠ No hay dispositivos inalámbricos en esta red.")
            return []
        channel_data = []
        for device in wireless_devices:
            try:
                data = dashboard.wireless.getNetworkWirelessChannelUtilizationHistory(
                    network_id, serial=device['serial'], timespan=86400
                )
                if data:
                    channel_data.extend(data)
            except Exception as e:
                print(f"❌ Error obteniendo datos de {device['serial']}: {e}")
        if not channel_data:
            print("⚠ No se encontraron datos de utilización de canales inalámbricos.")
        sorted_data = sorted(channel_data, key=lambda x: x['utilization']['total'], reverse=True)
        return sorted_data
    except Exception as e:
        return {"error": f"❌ Error en list_wireless_channels({network_id}): {e}"}


def list_vlans(network_id):
    """Listar las VLANs configuradas en una red específica."""
    try:
        data = dashboard.appliance.getNetworkApplianceVlans(network_id)
        return data
    except Exception as e:
        return {"error": f"❌ Error en list_vlans({network_id}): {e}"}


def list_saturated_ports(network_id):
    """Listar equipos con puertos de switch saturados en una red Meraki."""
    try:
        devices = dashboard.networks.getNetworkDevices(network_id)
        switches = [device for device in devices if device.get('model', '').startswith('MS')]
        if not switches:
            return "No se encontraron switches en esta red."
        saturated_ports = []
        for switch in switches:
            serial = switch.get('serial')
            ports = dashboard.switch.getDeviceSwitchPortsStatuses(serial)
            for port in ports:
                port_id = port.get("portId")
                usage = port.get("usageInKb", {}).get("total", 0)
                if port_id is not None and usage > 1000000:
                    saturated_ports.append({
                        "switch_serial": serial,
                        "port": port_id,
                        "usage_kb": usage
                    })
        if not saturated_ports:
            return "No se encontraron puertos saturados en los switches."
        saturated_ports.sort(key=lambda x: x["usage_kb"], reverse=True)
        return saturated_ports
    except Exception as e:
        return {"error": f"❌ Error en list_saturated_ports({network_id}): {e}"}

# ==============================================================================
# NUEVAS FUNCIONES PARA CAMARAS
# ==============================================================================

def clean_camera_filename(name: str) -> str:
    """
    Limpia el nombre de la cámara para que sea válido como nombre de archivo.
    """
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def list_cameras(*args, **kwargs) -> list:
    """
    Retorna una lista de nombres de cámaras (modelos que comienzan con 'MV') en la red Meraki.
    """
    devices = dashboard.networks.getNetworkDevices(NETWORK_ID)
    cameras = [d for d in devices if d.get("model", "").startswith("MV")]
    camera_names = []
    for cam in cameras:
        name = cam.get("name", cam.get("serial"))
        camera_names.append(clean_camera_filename(name))
    return camera_names

def get_camera_by_name(camera_name: str) -> dict:
    """
    Busca y retorna el diccionario de la cámara que coincida con el nombre proporcionado.
    Retorna None si no se encuentra.
    """
    devices = dashboard.networks.getNetworkDevices(NETWORK_ID)
    cameras = [d for d in devices if d.get("model", "").startswith("MV")]
    camera_name_clean = clean_camera_filename(camera_name)
    for cam in cameras:
        name = cam.get("name", cam.get("serial"))
        if clean_camera_filename(name) == camera_name_clean:
            return cam
    return None

def download_camera_image(camera_serial: str, camera_name: str) -> str:
    """
    Solicita un snapshot de la cámara mediante la API de Meraki y descarga la imagen.
    Retorna la ruta local donde se guardó la imagen.
    """
    response = dashboard.camera.generateDeviceCameraSnapshot(camera_serial)
    if "url" not in response:
        raise Exception("No se obtuvo URL de imagen. Verifica permisos o disponibilidad de la cámara.")
    snapshot_url = response["url"]
    time.sleep(10)  # Espera a que la imagen esté lista
    headers = {"User-Agent": "Mozilla/5.0"}
    img_response = requests.get(snapshot_url, headers=headers, stream=True)
    if img_response.status_code != 200:
        raise Exception(f"Error al descargar la imagen: {img_response.status_code} {img_response.reason}")
    if not os.path.exists(SAVE_PATH):
        os.makedirs(SAVE_PATH)
    img_path = os.path.join(SAVE_PATH, f"{camera_name}.jpg")
    with open(img_path, "wb") as f:
        for chunk in img_response.iter_content(1024):
            f.write(chunk)
    return img_path
"""
def analyze_camera(camera_input) -> str:
    
    Dado el nombre de una cámara (o un dict con la clave "camera_name"),
    descarga su snapshot, analiza la imagen usando la función 'analyze_image_to_json'
    y retorna el análisis en formato JSON.

    if isinstance(camera_input, str):
        try:
            camera_input = ast.literal_eval(camera_input)
        except Exception:
            pass
    if isinstance(camera_input, dict):
        camera_name = extract_value(camera_input, "camera_name")
    else:
        camera_name = camera_input
    if not camera_name or not isinstance(camera_name, str):
        return "❌ Error: No se proporcionó un nombre de cámara válido."
    cam = get_camera_by_name(camera_name)
    if cam is None:
        return f'No se encontró la cámara con nombre "{camera_name}"'
    camera_serial = cam.get("serial")
    camera_name_clean = clean_camera_filename(cam.get("name", camera_serial))
    try:
        img_path = download_camera_image(camera_serial, camera_name_clean)
        analysis = analyze_image_to_json(img_path)
        return analysis
    except Exception as e:
        return f"Error al analizar la cámara {camera_name}: {e}"
"""
# ==============================================================================
# CREACIÓN DE TOOLS PARA LANGCHAIN (REPORTES, CAMARAS Y FUNCIONES ANTIGUAS)
# ==============================================================================

list_organizations_tool = Tool(
    name="Listar Organizaciones",
    func=list_organizations,
    description="Devuelve una lista de organizaciones en la cuenta de Meraki."
)

list_networks_tool = Tool(
    name="Listar Redes",
    func=lambda org_data: list_networks(org_data.get("org_id") if isinstance(org_data, dict) else org_data),
    description="Devuelve el listado de redes de una organización. Requiere org_id."
)

list_devices_tool = Tool(
    name="Listar Dispositivos",
    func=lambda net_data: list_devices(net_data.get("network_id") if isinstance(net_data, dict) else net_data),
    description="Devuelve la lista de dispositivos en una red. Requiere network_id."
)

list_clients_tool = Tool(
    name="Listar Clientes",
    func=lambda net_data: list_clients(net_data.get("network_id") if isinstance(net_data, dict) else net_data),
    description="Devuelve la lista de clientes conectados en una red. Requiere network_id."
)

get_subscription_end_date_tool = Tool(
    name="Fecha de Suscripción",
    func=lambda org_data: get_subscription_end_date(org_data.get("org_id") if isinstance(org_data, dict) else org_data),
    description="Devuelve la fecha de expiración de la suscripción de una organización. Requiere org_id."
)

get_network_status_tool = Tool(
    name="Estado de la Red",
    func=get_network_status,
    description="Devuelve un reporte con el total de dispositivos y clientes en una red. Requiere network_id."
)

list_firewall_rules_tool = Tool(
    name="Listar Reglas de Firewall",
    func=list_firewall_rules,
    description="Devuelve las reglas de firewall configuradas en una red. Requiere network_id."
)

list_wireless_channels_tool = Tool(
    name="Listar Canales Inalámbricos",
    func=list_wireless_channels,
    description="Devuelve los canales inalámbricos ordenados por saturación en una red. Requiere network_id."
)

list_vlans_tool = Tool(
    name="Listar VLANs",
    func=list_vlans,
    description="Devuelve las VLANs configuradas en una red. Requiere network_id."
)

list_saturated_ports_tool = Tool(
    name="Listar Puertos Saturados",
    func=list_saturated_ports,
    description="Devuelve un reporte de puertos de switches saturados en una red. Requiere network_id."
)

# Nuevos tools para cámaras
list_cameras_tool = Tool(
    name="Listar Cámaras",
    func=list_cameras,
    description="Devuelve una lista de nombres de cámaras (modelos que comienzan con 'MV') en la red Meraki."
)
"""
analyze_camera_tool = Tool(
    name="Analizar Imagen de Cámara",
    func=analyze_camera,
    description=(
        "Dado el nombre de una cámara (o un dict con la clave 'camera_name'), descarga su snapshot, "
        "analiza la imagen (por ejemplo, para contar cuántas personas hay) y devuelve el resultado en formato JSON."
    )
)
"""

tools_meraki = [
    list_organizations_tool,
    list_networks_tool,
    list_devices_tool,
    list_clients_tool,
    get_subscription_end_date_tool,
    get_network_status_tool,
    list_firewall_rules_tool,
    list_wireless_channels_tool,
    list_vlans_tool,
    list_saturated_ports_tool,
    list_cameras_tool,
    # analyze_camera_tool
]


def main():
    print("=== Pruebas de funciones nuevas de Meraki Utils ===")

    # Probar listar reglas de firewall
    try:
        print("\n🔹 Listando reglas de firewall:")
        firewall_rules = list_firewall_rules(NETWORK_ID)
        print(json.dumps(firewall_rules, indent=4))
    except Exception as e:
        print("Error al listar reglas de firewall:", e)

    # Probar listar canales inalámbricos
    try:
        print("\n🔹 Listando canales inalámbricos:")
        wireless_channels = list_wireless_channels(NETWORK_ID)
        print(json.dumps(wireless_channels, indent=4))
    except Exception as e:
        print("Error al listar canales inalámbricos:", e)

    # Probar listar VLANs
    try:
        print("\n🔹 Listando VLANs:")
        vlans = list_vlans(NETWORK_ID)
        print(json.dumps(vlans, indent=4))
    except Exception as e:
        print("Error al listar VLANs:", e)

    # Probar listar puertos saturados
    try:
        print("\n🔹 Listando puertos saturados:")
        saturated_ports = list_saturated_ports(NETWORK_ID)
        if isinstance(saturated_ports, list):
            print(json.dumps(saturated_ports, indent=4))
        else:
            print(saturated_ports)
    except Exception as e:
        print("Error al listar puertos saturados:", e)

    # Probar listar cámaras
    try:
        print("\n🔹 Listando cámaras:")
        cameras = list_cameras()
        print(json.dumps(cameras, indent=4))
    except Exception as e:
        print("Error al listar cámaras:", e)

    # Probar análisis de imagen de cámara
    try:
        print("\n🔹 Analizando imagen de cámara (ejemplo):")
        # analysis = analyze_camera("BVSP-SI-CAM03 | Data Center")
        # print(analysis)
    except Exception as e:
        print("Error al analizar cámara:", e)


if __name__ == "__main__":
    main()
