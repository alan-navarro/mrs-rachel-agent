from flask import Flask, request
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
