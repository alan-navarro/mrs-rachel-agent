from flask import Flask, request, jsonify
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
from customer_payload import *
from auto_messaging_response import *
from state import get_user, reset_user
from router import route_message
from responses import RESPONSES
from datetime import datetime
from datetime import datetime, timezone

load_dotenv()
env_path = Path('.')/'.env'
bp = "\n"*3

TWILIO_SID = os.environ["TWILIO_SID"]
TWILIO_TOKEN = os.environ["TWILIO_TOKEN"]
SENDER_NUMBER = os.environ["SENDER_NUMBER"]
ADMIN_NUMBER = os.environ["ADMIN_NUMBER"]
created_at = datetime.now()


app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    # Returning a 200 status code tells the monitor "I'm alive!"
    return jsonify({"status": "healthy", "message": "App is awake"}), 200

@app.route('/')
def main_index():
    return "Hello! This is my Python app on Koyeb."

@app.route("/webhook_whatsapp", methods=["POST"])
def whatsapp_webhook():

    data = request.form.to_dict()
    GET_FROM_NUMBER = data.get("From")
    FROM_NUMBER = GET_FROM_NUMBER.replace("whatsapp:+", "")

    message_text = data.get("Body", "").strip()
    num_media = int(data.get("NumMedia", 0))
    customer_details = CustomerPayload(data)
    user = get_user(FROM_NUMBER)
    lang = user.get("lang") or "es"

    resp = MessagingResponse()

    print(bp,customer_details,bp,FROM_NUMBER,bp,ADMIN_NUMBER,bp,user,bp,message_text,bp)

    if FROM_NUMBER == ADMIN_NUMBER:
        print(bp, data, bp,FROM_NUMBER,bp,ADMIN_NUMBER,bp)
    
        # Recupera texto desde button_reply, message o Body
        message_text = (
            getattr(customer_details, "button_reply", None)
            or getattr(customer_details, "message", None)
            or data.get("Body", "").strip()
        )
    
        # ---------------------------
        # CONFIRMACIÓN POR ID O TEL
        # ---------------------------
        if message_text.isdigit():
            code_id = int(message_text)
            print("🔎 Admin sent numeric value:", code_id)
    
            try:
                # Intentamos confirmar como ID de tabla
                recovered_phone_number = PullShopify().confirm_discount_code(code_id)

                # ✅ FIX 1 — obtener idioma DEL CLIENTE
                client_user = get_user(str(recovered_phone_number))
                lang = client_user.get("lang", "es")

                if lang not in ["es", "en", "fr"]:
                    lang = "es"

                # 📩 Mensaje de confirmación (multi-idioma)
                client.messages.create(
                    from_="whatsapp:+" + SENDER_NUMBER,
                    to="whatsapp:+" + str(recovered_phone_number),
                    body=RESPONSES["PAYMENT_CONFIRMED"][lang]
                )
                out = PullShopify().make_100pct_discount(prefix="FREE100", usage_limit=1)
                update_discount_code_table = PullShopify().update_discount_code_by_id(code_id, out["discount_code"])


                client.messages.create(
                    from_="whatsapp:+" + SENDER_NUMBER,
                    to="whatsapp:+" + str(recovered_phone_number),
                    body=f"{out["discount_code"]}"
                    )
                
                client.messages.create(
                    from_="whatsapp:+" + SENDER_NUMBER,
                    to="whatsapp:+" + str(recovered_phone_number),
                    body=RESPONSES["END"][lang]
                    )
    
            except Exception as e:
                # Si NO existe ese ID → se interpreta como TELÉFONO
                print("⚠️ No existe el ID. Tratando como teléfono:", message_text)
    
                client_user = get_user(message_text)
                lang = client_user.get("lang", "es")

                if lang not in ["es", "en", "fr"]:
                    lang = "es"

                client.messages.create(
                    from_="whatsapp:+" + SENDER_NUMBER,
                    to="whatsapp:+" + message_text,
                    body=RESPONSES["PAYMENT_NOT_RECEIVED"][lang]
                )
                return "OK", 200

        else:
            print("ℹ️ Mensaje ignorado (ni número ni 'no'):", message_text)
            return "OK", 200
    else:

# ------------------------------------------------
    # 1️⃣ MEDIA RECEIVED (COMPROBANTE)
    # ------------------------------------------------
        if num_media > 0:
            # ✅ Esta línea se ejecutará SIEMPRE que haya una imagen
            AutoMessagingResponse().forward_media_delete_record_contact_admin(
                FROM_NUMBER,
                num_media
            )
    
            # Si quieres enviar una respuesta distinta según si es la primera vez o re-envío
            if user.get("step") == "WAITING_TRANSFER_PROOF":
                resp.message(RESPONSES["TRANSFER_PROOF_RECEIVED"][lang])
                # Cambiamos el estado solo la primera vez
                user["step"] = "WAITING_ADMIN_CONFIRMATION"
            else:
                # Opcional: Un mensaje por si vuelve a enviar fotos
                resp.message("Hemos recibido tus archivos adicionales.")
    
            return str(resp), 200

        # ------------------------------------------------
        # 2️⃣ TEXTO NORMAL
        # ------------------------------------------------
        key = route_message(message_text, user)
        lang = user["lang"] if user.get("lang") else "es"

        # Mensaje principal
        resp.message(RESPONSES[key][lang])

        # ------------------------------------------------
        # 3️⃣ CASO ESPECIAL: TRANSFER
        # ------------------------------------------------
        if key == "TRANSFER":
            PullShopify().first_entry_into_discount_codes(FROM_NUMBER, created_at)

            resp.message(RESPONSES["TRANSFER_FOLLOWUP"][lang])

            # 🔑 CLAVE: ahora esperamos comprobante
            user["step"] = "WAITING_TRANSFER_PROOF"

        elif key == "END":
            reset_user(FROM_NUMBER)


    return str(resp), 200

@app.route("/shopify/orders/create", methods=["POST"])
def webhook_new_order():
    data = request.get_json()

    print("📥 Recibido Webhook de Shopify (orden nueva)")

    # 1️⃣ Insertar SOLO la orden del webhook
    discount_code = PullShopify().insert_single_order_from_webhook(data)

    # 2️⃣ Si existe discount code, ejecuta tu lógica existente
    if discount_code:
        PullShopify().update_order_id_by_discount(discount_code)

    return "ok", 200


def pag_not_found (error):
    return "<h1> Página no encontrada </h1>", 404

if __name__ == "__main__":
    app.run(debug=True)
# import os
# from flask import Flask, request, jsonify
# from twilio.twiml.messaging_response import MessagingResponse
# from datetime import datetime
# from pathlib import Path
# from dotenv import load_dotenv
# import threading
# # Importaciones de tus módulos locales
# from customer_payload import CustomerPayload
# from auto_messaging_response import AutoMessagingResponse
# from pull_shopify import PullShopify
# from state import get_user, reset_user
# from router import route_message
# from responses import RESPONSES

# # Cargar variables de entorno
# load_dotenv()
# env_path = Path('.') / '.env'
# load_dotenv(dotenv_path=env_path)

# app = Flask(__name__)

# # Configuración global básica
# SENDER_NUMBER = os.environ.get("SENDER_NUMBER")
# ADMIN_NUMBER = os.environ.get("ADMIN_NUMBER")
# bp = "\n"*3

# @app.route('/health', methods=['GET'])
# def health_check():
#     # Returning a 200 status code tells the monitor "I'm alive!"
#     return jsonify({"status": "healthy", "message": "App is awake"}), 200

# @app.route('/')
# def main_index():
#     return "Hello! This is my Python app on Koyeb."

# @app.route("/webhook_whatsapp", methods=["POST"])
# def whatsapp_webhook():
#     # --- CHIVATO DE DEPLOY ---
#     print("\n" + "="*30)
#     print("⚡ VERSIÓN: PERSISTENCIA TOTAL IDIOMA + STEP ⚡")
#     print("="*30 + "\n")

#     data = request.form.to_dict()
#     from_number_clean = data.get("From", "").replace("whatsapp:+", "")
#     message_text = data.get("Body", "").strip()
#     num_media = int(data.get("NumMedia", 0))

#     # 1. RECUPERACIÓN DE ESTADO INICIAL
#     user = get_user(from_number_clean)
#     if not user:
#         user = {"lang": "es", "step": "LANG"}
    
#     lang = user.get("lang") or "es" 

#     # 2. LÓGICA DE BASE DE DATOS (Sincronización de idioma y avance de paso)
#     try:
#         new_lang_selection = None
#         # Si el usuario está en el paso de elegir idioma
#         if user.get("step") == "LANG":
#             mapping = {"1": "es", "2": "en", "3": "fr"}
#             new_lang_selection = mapping.get(message_text)

#         # La función manage_user_language ahora también debe actualizar el STEP a 'WELCOME'
#         # si recibe un new_lang_selection válido.
#         db_lang = PullShopify().manage_user_language(from_number_clean, new_lang_selection)
        
#         if db_lang != "undefined":
#             lang = db_lang
#             # Si acaba de seleccionar idioma, actualizamos el objeto local para esta ejecución
#             if new_lang_selection:
#                 user["step"] = "WELCOME"
            
#         user["lang"] = lang
#         print(f"DEBUG: Idioma recuperado de BD para {from_number_clean} es {lang} | Step: {user.get('step')}")

#     except Exception as e:
#         print(f"⚠️ Error recuperando idioma de BD: {e}. Usando fallback: {lang}")

#     resp = MessagingResponse()

#     # ------------------------------------------------
#     # LÓGICA PARA EL ADMIN (Confirmación de Pagos)
#     # ------------------------------------------------
#     if from_number_clean == ADMIN_NUMBER:
#         if message_text.isdigit():
#             code_id = int(message_text)
#             try:
#                 recovered_phone = PullShopify().confirm_discount_code(code_id)
                
#                 # Consultamos idioma del cliente en la BD
#                 c_lang_db = PullShopify().manage_user_language(str(recovered_phone))
#                 c_lang = "es" if c_lang_db == "undefined" else c_lang_db

#                 out = PullShopify().make_100pct_discount(prefix="FREE100", usage_limit=1)
#                 new_coupon = out.get("discount_code", "ERROR_GEN")
#                 PullShopify().update_discount_code_by_id(code_id, new_coupon)

#                 from twilio.rest import Client
#                 tw_client = Client(os.environ["TWILIO_SID"], os.environ["TWILIO_TOKEN"])
#                 tw_from = f"whatsapp:+{SENDER_NUMBER}"
#                 tw_to = f"whatsapp:+{recovered_phone}"
                
#                 tw_client.messages.create(from_=tw_from, to=tw_to, body=RESPONSES["PAYMENT_CONFIRMED"][c_lang])
#                 tw_client.messages.create(from_=tw_from, to=tw_to, body=f"🎫 *{new_coupon}*")
#                 tw_client.messages.create(from_=tw_from, to=tw_to, body=RESPONSES["END"][c_lang])
                
#                 print(f"✅ Cupón {new_coupon} enviado a {recovered_phone} en {c_lang}")
#             except Exception as e:
#                 print(f"❌ ERROR ADMIN: {e}")
#         return "OK", 200

#     # ------------------------------------------------
#     # LÓGICA PARA EL CLIENTE
#     # ------------------------------------------------
    
#     # Manejo de imágenes (Transferencias)
#     if num_media > 0:
#         discount_id = "N/A"
#         try:
#             discount_id = PullShopify().get_latest_id_for_phone(from_number_clean)
#         except: pass

#         threading.Thread(target=AutoMessagingResponse().forward_media_to_admin, 
#                          args=(from_number_clean, num_media, data, discount_id)).start()

#         # Determinamos la llave de respuesta
#         msg_key = "TRANSFER_PROOF_RECEIVED" if user.get("step") == "WAITING_TRANSFER_PROOF" else "WELCOME"
        
#         # Buscamos la traducción o fallback
#         texto_media = RESPONSES.get(msg_key, {}).get(lang, RESPONSES.get(msg_key, {}).get("es", "Gracias."))
#         resp.message(texto_media)
        
#         user["step"] = "WAITING_ADMIN_CONFIRMATION"
#         return str(resp), 200

#     # Manejo de texto normal
#     try:
#         key = route_message(message_text, user)
        
#         # Sincronizamos idioma por si cambió en route_message
#         lang = user.get("lang", lang)

#         if not key or key not in RESPONSES:
#             key = "WELCOME"
            
#         # Obtenemos texto traducido
#         texto_final = RESPONSES[key].get(lang, RESPONSES[key].get("es", "Hola"))
#         resp.message(texto_final)

#         if key == "TRANSFER":
#             PullShopify().first_entry_into_discount_codes(from_number_clean, datetime.now())
            
#             # Mensaje de seguimiento traducido
#             follow_up = RESPONSES.get("TRANSFER_FOLLOWUP", {}).get(lang, RESPONSES.get("TRANSFER_FOLLOWUP", {}).get("es", "..."))
#             resp.message(follow_up)
            
#             user["step"] = "WAITING_TRANSFER_PROOF"
#         elif key == "END":
#             reset_user(from_number_clean)

#     except Exception as e:
#         print(f"💥 Error Webhook Texto: {e}")
#         resp.message("Lo siento, hubo un error. Intenta de nuevo.")

#     return str(resp), 200

# @app.route("/shopify/orders/create", methods=["POST"])
# def webhook_new_order():
#     data = request.get_json()
#     print("📥 Webhook Shopify: Nueva orden recibida")
#     discount_code = PullShopify().insert_single_order_from_webhook(data)
#     if discount_code:
#         PullShopify().update_order_id_by_discount(discount_code)
#     return "ok", 200

# @app.errorhandler(404)
# def page_not_found(error):
#     return "<h1>Página no encontrada</h1>", 404

# if __name__ == "__main__":
#     # Importante: Puerto 5000 por defecto para Flask
#     app.run(port=5000, debug=True)