import random
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

class InfluxDBService:
    def __init__(self):
        self.url = "https://us-east-1-1.aws.cloud2.influxdata.com"
        self.token = "YGfyFK9H_UEmCOgKFEPo9THbBe9l_8cYhp00G3GwFRZKTkevrsvAA4NPYwjNltbD9T2wR48XHdr5BqZzPVsIKg=="
        self.org = "UABC_Manufactura"
        self.bucket = "telemetria_gemelos"
        self.connected = False
        self._conectar()

    def _conectar(self):
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                timeout=5000
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            self.connected = True
        except Exception as e:
            print(f"[InfluxDB Error] {e}")
            self.connected = False

    def registrar_metricas_activo(self, linea_id: str, activo_id: str, variables_dict: dict, estado: str = "Operando"):
        """Registra un conjunto dinámico de variables de un activo en InfluxDB Cloud."""
        if not self.connected:
            self._conectar()

        point = (
            Point("telemetria_activo")
            .tag("linea_id", str(linea_id))
            .tag("activo_id", str(activo_id))
            .field("estado_operativo", str(estado))
        )

        for clave, val in variables_dict.items():
            if isinstance(val, (int, float)):
                point.field(clave, round(float(val), 2))
            elif isinstance(val, str):
                point.field(clave, val)

        point.time(datetime.now(timezone.utc))

        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
            return True
        except Exception as e:
            print(f"[InfluxDB Error] Fallo al escribir: {e}")
            return False

    def obtener_ultimas_metricas_activo(self, activo_id: str):
        if self.connected:
            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: -24h)
              |> filter(fn: (r) => r["_measurement"] == "telemetria_activo")
              |> filter(fn: (r) => r["activo_id"] == "{activo_id}")
              |> last()
            '''
            try:
                tables = self.query_api.query(query, org=self.org)
                metricas = {}
                for table in tables:
                    for record in table.records:
                        metricas[record.get_field()] = record.get_value()
                if metricas:
                    return metricas
            except Exception as e:
                print(f"[InfluxDB Error] Fallo consulta: {e}")

        return {}