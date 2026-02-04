from flask import request
import threading
import requests
import json
from requests.structures import CaseInsensitiveDict
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
import os
from twilio.rest import Client
import boto3
import uuid
import tempfile
from pull_shopify import *
import time
load_dotenv()
env_path = Path('.')/'.env'
load_dotenv(dotenv_path=env_path)

TWILIO_SID = os.environ["TWILIO_SID"]
TWILIO_TOKEN = os.environ["TWILIO_TOKEN"]
SENDER_NUMBER = os.environ["SENDER_NUMBER"]
ADMIN_NUMBER = os.environ["ADMIN_NUMBER"]
AWS_S3_BUCKET = os.environ["AWS_S3_BUCKET"]

    # AWS S3
s3 = boto3.client(
"s3",
aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
region_name=os.getenv("AWS_REGION"),
)   

client = Client(TWILIO_SID, TWILIO_TOKEN)


bp = "\n"*3

class AutoMessagingResponse:
    def __init__(self):
        return

    def CLABE_message(self, bot_phone_number, customer_phone_number):


        # 💬 Enviar mensaje de WhatsApp
        message = client.messages.create(
            from_="whatsapp:+" + bot_phone_number,  # Número oficial de Twilio WhatsApp
            body="#️⃣ CLABE Santander",
            to="whatsapp:+"+customer_phone_number     # Número del destinatario con código de país
        )
        message = client.messages.create(
            from_="whatsapp:+" + bot_phone_number,  # Número oficial de Twilio WhatsApp
            body="*44330009393104737*",
            to="whatsapp:+"+customer_phone_number     # Número del destinatario con código de país
        )

        PullShopify().first_entry_into_discount_codes(customer_phone_number, created_at)
        print(f"Mensaje enviado con SID: {message.sid}")
        return 

    # def upload_to_s3(self, local_path, mime_type):
    #     """Upload file to S3 and return public URL AND file key."""
    #     ext = mime_type.split("/")[-1]
    #     file_key = f"media/{uuid.uuid4()}.{ext}"    

    #     s3.upload_file(
    #         Filename=local_path,
    #         Bucket=AWS_S3_BUCKET,
    #         Key=file_key,
    #         ExtraArgs={
    #             "ContentType": mime_type,
    #             # "ACL": "public-read"  # required so Twilio can fetch it
    #         }
    #     )   

    #     public_url = f"https://{AWS_S3_BUCKET}.s3.amazonaws.com/{file_key}"
    #     # RETURN THE KEY ALONGSIDE THE URL
    #     return public_url, file_key
    
#     def forward_media_delete_record_contact_admin(self, from_number, num_media):
#         from_number = request.form.get("From")
#         num_media = int(request.form.get("NumMedia", 0))    

#         if num_media > 0:
#             forward_urls = []
#             s3_keys_to_delete = []  # S3 keys para borrar después   

#             for i in range(num_media):
#                 media_url = request.form.get(f"MediaUrl{i}")
#                 mime_type = request.form.get(f"MediaContentType{i}")    

#                 print("📎 MIME recibido:", mime_type)   

#                 # ---- EXTENSION SEGÚN MIME ----
#                 ext = {
#                     "image/jpeg": ".jpg",
#                     "image/png": ".png",
#                     "image/webp": ".webp",
#                     "image/heic": ".heic",
#                     "image/heif": ".heif",
#                     "application/pdf": ".pdf"
#                 }.get(mime_type, "")   # Si no existe, no le ponemos extensión  

#                 # ---- Descargar desde Twilio ----
#                 media_res = requests.get(
#                     media_url,
#                     auth=(os.getenv("TWILIO_SID"), os.getenv("TWILIO_TOKEN"))
#                 )   

#                 if media_res.status_code != 200:
#                     print("❌ Failed to download media:", media_res.text)
#                     continue    

#                 # ---- Crear archivo temporal con extensión correcta ----
#                 temp_dir = tempfile.gettempdir()
#                 temp_filename = f"{uuid.uuid4()}{ext}"
#                 temp_path = os.path.join(temp_dir, temp_filename)   

#                 # Guardar archivo localmente
#                 with open(temp_path, "wb") as f:
#                     f.write(media_res.content)  

#                 # ---- Subir a S3 ----
#                 public_url, file_key = AutoMessagingResponse().upload_to_s3(temp_path, mime_type)
#                 forward_urls.append(public_url)
#                 s3_keys_to_delete.append(file_key)  

#                 # Borrar archivo temporal
#                 os.remove(temp_path)    

#             # ---- Forward to admin ----
#             from_number_ = from_number.replace("whatsapp:+", "")
#             get_discount_code_id = PullShopify().get_latest_id_for_phone(from_number_)  

#             text_message = f'''💰📲 Revisa tu app de *Santander*:   

# * Para confirmar pago escribe: 

# *{get_discount_code_id}* 

# * Para solicitarlo otra vez copia y pega este número: 

# {from_number_}''' 

#             message = client.messages.create(
#                 from_="whatsapp:+" + SENDER_NUMBER,
#                 to="whatsapp:+" + ADMIN_NUMBER,
#                 body=text_message,
#                 media_url=forward_urls
#             )   

#             print(f"Message forwarded successfully. SID: {message.sid}")    

#             # ---- ELIMINAR ARCHIVOS DE S3 DESPUÉS DE ENVIAR ----
#             for key in s3_keys_to_delete:
#                 try:
#                     s3.delete_object(Bucket=AWS_S3_BUCKET, Key=key)
#                     print(f"✅ Deleted S3 object: {key}")
#                 except Exception as e:
#                     print(f"❌ Failed to delete S3 object {key}: {e}")  

#         return "OK", 200
    def upload_to_s3(self, local_path, mime_type):
        """Sube archivo a S3 y retorna URL pública y la llave."""
        ext = mime_type.split("/")[-1]
        file_key = f"media/{uuid.uuid4()}.{ext}"
        
        s3.upload_file(
            Filename=local_path,
            Bucket=AWS_S3_BUCKET,
            Key=file_key,
            ExtraArgs={"ContentType": mime_type}
        )
        public_url = f"https://{AWS_S3_BUCKET}.s3.amazonaws.com/{file_key}"
        return public_url, file_key

    def delayed_delete(self, s3_keys, delay=600):
        """Espera el tiempo definido y elimina los objetos de S3."""
        print(f"🕒 Iniciando temporizador de {delay}s para borrar {len(s3_keys)} archivos...")
        time.sleep(delay)
        for key in s3_keys:
            try:
                s3.delete_object(Bucket=AWS_S3_BUCKET, Key=key)
                print(f"✅ Objeto eliminado de S3: {key}")
            except Exception as e:
                print(f"❌ Error al eliminar {key}: {e}")

    def forward_media_to_admin(self, from_number_clean, num_media, form_data, discount_id):
        """Procesa, sube y reenvía imágenes al admin."""
        forward_urls = []
        s3_keys_to_delete = []

        for i in range(num_media):
            media_url = form_data.get(f"MediaUrl{i}")
            mime_type = form_data.get(f"MediaContentType{i}")

            # Extensiones comunes
            ext = {
                "image/jpeg": ".jpg", 
                "image/png": ".png",
                "image/webp": ".webp", 
                "application/pdf": ".pdf"
            }.get(mime_type, "")

            # Descarga de Twilio
            media_res = requests.get(media_url, auth=(TWILIO_SID, TWILIO_TOKEN))
            if media_res.status_code != 200:
                continue

            # Archivo temporal
            temp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}{ext}")
            with open(temp_path, "wb") as f:
                f.write(media_res.content)

            # Subida a S3
            public_url, file_key = self.upload_to_s3(temp_path, mime_type)
            forward_urls.append(public_url)
            s3_keys_to_delete.append(file_key)
            os.remove(temp_path)

        # Mensaje al Admin
        text_message = (
            f"💰📲 *Pago recibido de: {from_number_clean}*\n\n"
            f"* Para confirmar escribe:\n*{discount_id}*\n\n"
            f"* Para rechazar copia el tel:\n{from_number_clean}"
        )

        message = client.messages.create(
            from_=f"whatsapp:+{SENDER_NUMBER}",
            to=f"whatsapp:+{ADMIN_NUMBER}",
            body=text_message,
            media_url=forward_urls
        )
        print(f"🚀 Reenvío al admin exitoso. SID: {message.sid}")

        # Lanzar borrado en 10 minutos (600 segundos) sin bloquear el bot
        if s3_keys_to_delete:
            threading.Thread(target=self.delayed_delete, args=(s3_keys_to_delete, 600)).start()

        return message.sid