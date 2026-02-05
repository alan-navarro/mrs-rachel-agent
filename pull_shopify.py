
import requests
import re
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
import json
from datetime import datetime
import pandas as pd
from psycopg2.extras import execute_values
from datetime import datetime, timezone
import random
import string


load_dotenv()
SHOPIFY_ACCESS_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
HOST_DB = os.environ["HOST_DB"]
USER_DB = os.environ["USER_DB"]
PASSWORD_DB = os.environ["PASSWORD_DB"]
DATABASE = os.environ["DATABASE"]
API_VERSION = "2024-10"

bp = "\n"*3
created_at = datetime.now()

def create_conn():
    CONN = psycopg2.connect(
                host = HOST_DB,
                user = USER_DB,
                password = PASSWORD_DB,
                database = DATABASE,
                sslmode="require"
            )
    
    return CONN


class PullShopify:

        def orders_to_dataframe(self, orders):
            rows = []

            for order in orders:
                customer = order.get("customer", {}) or {}
                shipping = order.get("shipping_address", {}) or {}
                billing = order.get("billing_address", {}) or {}

                fulfillments = order.get("fulfillments", []) or []

                # =====================================================
                # 🔥 Lógica robusta para fulfillment_status_resolved
                # =====================================================
                if len(fulfillments) == 0:
                    fulfillment_status_resolved = "UNFULFILLED"
                else:
                    statuses = [f.get("status", "").lower() for f in fulfillments]

                    if all(s in ("success", "fulfilled") for s in statuses):
                        fulfillment_status_resolved = "FULFILLED"
                    elif any(s in ("success", "fulfilled") for s in statuses):
                        fulfillment_status_resolved = "PARTIALLY_FULFILLED"
                    elif all(s in ("pending", "open") for s in statuses):
                        fulfillment_status_resolved = "IN_PROGRESS"
                    elif all(s in ("cancelled", "restocked") for s in statuses):
                        fulfillment_status_resolved = "FULFILLMENT_CANCELLED"
                    else:
                        fulfillment_status_resolved = "UNFULFILLED"

                # =====================================================
                # 🟢 Nueva columna simplificada para tu análisis:
                #    "FULFILLED" vs "UNFULFILLED"
                # =====================================================

                if len(fulfillments) > 0 and all(
                    f.get("status", "").lower() in ("success", "fulfilled")
                    for f in fulfillments
                ):
                    is_fulfilled = "FULFILLED"
                else:
                    is_fulfilled = "UNFULFILLED"

                # =====================================================

                rows.append({
                    "order_id": order["id"],
                    "order_name": order.get("name"),
                    "created_at": order.get("created_at"),
                    "total_price": order.get("total_price"),
                    "subtotal_price": order.get("subtotal_price"),
                    "total_tax": order.get("total_tax"),
                    "currency": order.get("currency"),
                    "financial_status": order.get("financial_status"),
                    "fulfillment_status": order.get("fulfillment_status"),
                    "fulfillments": fulfillments,

                    # columnas nuevas
                    "fulfillment_status_resolved": fulfillment_status_resolved,
                    "is_fulfilled": is_fulfilled,

                    "tags": order.get("tags"),
                    "note": order.get("note"),

                    # Customer
                    "customer_id": customer.get("id"),
                    "customer_email": customer.get("email"),
                    "customer_first_name": customer.get("first_name"),
                    "customer_last_name": customer.get("last_name"),
                    "customer_phone": customer.get("phone"),

                    # Shipping
                    "shipping_address1": shipping.get("address1"),
                    "shipping_city": shipping.get("city"),
                    "shipping_zip": shipping.get("zip"),
                    "shipping_country": shipping.get("country"),
                    "shipping_phone": shipping.get("phone"),

                    # Billing
                    "billing_address1": billing.get("address1"),
                    "billing_city": billing.get("city"),
                    "billing_zip": billing.get("zip"),
                    "billing_country": billing.get("country")
                })

            df = pd.DataFrame(rows)
            return df



        def get_orders(self,limit=50):
            url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/orders.json?limit={limit}"

            headers = {
                "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            }

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                print("Error:", response.text)
                return []

            data = response.json()
            return data["orders"]


        def get_all_orders_df(self):
            """
            Descarga TODAS las órdenes de Shopify,
            normaliza los campos necesarios y regresa un DataFrame
            con los core_columns solicitados.
            """
            import pandas as pd
            import requests

            url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/orders.json"
            headers = {
                "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            }
            params = {
                "status": "any",
                "fulfillment_status": "any",
                "financial_status": "any",
                "limit": 250
            }

            # --- Descarga paginada ---
            all_orders = []
            next_page = None

            while True:
                if next_page:
                    response = requests.get(next_page, headers=headers)
                else:
                    response = requests.get(url, headers=headers, params=params)

                data = response.json()
                orders = data.get("orders", [])
                all_orders.extend(orders)

                link_header = response.headers.get("Link")
                if link_header and 'rel="next"' in link_header:
                    next_page = link_header.split("<")[1].split(">")[0]
                else:
                    break
                
            # --- Normalizar Shopify JSON ---
            df = pd.json_normalize(all_orders, max_level=2)

            # --- Extraer campos personalizados ---

            # discount_codes → True/False
            df["discount_codes_flag"] = df["discount_codes"].apply(lambda x: True if isinstance(x, list) and len(x) > 0 else False)

            # discount_codes.code
            df["discount_code"] = df["discount_codes"].apply(
                lambda x: x[0].get("code") if isinstance(x, list) and len(x) > 0 else None
            )

            # line_items.product_id
            df["product_id"] = df["line_items"].apply(
                lambda x: x[0].get("product_id") if isinstance(x, list) and len(x) > 0 else None
            )

            # line_items.name
            df["product_name"] = df["line_items"].apply(
                lambda x: x[0].get("name") if isinstance(x, list) and len(x) > 0 else None
            )

            # properties booking → Date + Time
            def extract_booking(properties):
                if not isinstance(properties, list) or len(properties) < 2:
                    return None
                try:
                    return f"{properties[0]['value']} {properties[1]['value']}"
                except:
                    return None

            df["booking"] = df["line_items"].apply(
                lambda x: extract_booking(x[0].get("properties")) if isinstance(x, list) and len(x) > 0 else None
            )

            # vendor
            df["vendor"] = df["line_items"].apply(
                lambda x: x[0].get("vendor") if isinstance(x, list) and len(x) > 0 else None
            )

            # province & country desde billing_address (más consistente que shipping)
            df["province"] = df.get("billing_address.province")
            df["country"] = df.get("billing_address.country")

            # --- Selección final de columnas ---
            core_columns = [
                "app_id",
                "order_number",
                "contact_email",
                "created_at",
                "currency",
                "current_subtotal_price",
                "current_total_price",
                "current_total_discounts",
                "customer_locale",
                "discount_codes_flag",
                "discount_code",
                "total_discounts",
                "processed_at",
                "fulfillment_status",
                "product_id",
                "product_name",
                "booking",
                "vendor",
                "province",
                "country",
            ]

            return df[core_columns]

        def first_entry_into_discount_codes(self, phone_number, created_at):
            CONN = create_conn()

            try:
                with CONN:
                    with CONN.cursor() as cur:
                        insert_query = """
                            INSERT INTO discount_codes (
                                phone_number,
                                created_at,
                                code,
                                confirmed_payment,
                                code_used_at
                            )
                            VALUES (%s, %s, %s, %s, %s);
                        """
                        cur.execute(
                            insert_query, 
                            (phone_number, created_at, None, "requested", None)
                        )
                        print("✅ Registro guardado correctamente.")
            except Exception as e:
                print("❌ Error al insertar:", e)

        def update_discount_codes(self, phone_number, created_at):
            CONN = create_conn()

            try:
                with CONN:
                    with CONN.cursor() as cur:
                        insert_query = """
                            INSERT INTO discount_codes (
                                phone_number,
                                created_at,
                                code,
                                confirmed_payment,
                                code_used_at
                            )
                            VALUES (%s, %s, %s, %s, %s);
                        """
                        cur.execute(
                            insert_query, 
                            (phone_number, created_at, None, None, None)
                        )
                        print("✅ Registro guardado correctamente.")
            except Exception as e:
                print("❌ Error al insertar:", e)


        def log_and_get_lang(self, phone_number, message_text, current_step):
            conn = None
            valid_langs = {"ES": "es", "EN": "en", "FR": "fr"}
            choice = message_text.strip().upper()

            try:
                conn = create_conn() # Usa tu factory de conexión
                cur = conn.cursor()

                # 1. Buscar el idioma más reciente del historial
                cur.execute("""
                    SELECT lang FROM chatbot_interaction 
                    WHERE phone_number = %s 
                    ORDER BY created_at DESC LIMIT 1
                """, (str(phone_number),))
                result = cur.fetchone()
                last_lang = result[0] if result else None

                # 2. Definir idioma actual: si elige uno nuevo o hereda el anterior
                lang_to_use = valid_langs.get(choice, last_lang)

                # 3. Insertar registro de esta nueva interacción (Log)
                if lang_to_use:
                    cur.execute("""
                        INSERT INTO chatbot_interaction (phone_number, lang, step, created_at)
                        VALUES (%s, %s, %s, NOW())
                    """, (str(phone_number), lang_to_use, current_step))
                    conn.commit()

                return lang_to_use
            except Exception as e:
                print(f"Error DB Lang: {e}")
                return last_lang or "es"
            finally:
                if conn:
                    cur.close()
                    conn.close()



        def get_all_orders_to_db(self):
            """
            Descarga TODAS las órdenes de Shopify, normaliza los campos necesarios
            y las inserta SOLO si son nuevas (según order_number) en PostgreSQL.
            Devuelve el discount_code más reciente (o None).
            """

            # -----------------------------
            # 🔌 Conexión a PostgreSQL
            # -----------------------------
            CONN = create_conn()
            cursor = CONN.cursor()

            try:
                # ======================================================
                # 1) Obtener order_number ya existentes
                # ======================================================
                cursor.execute("SELECT order_number FROM shopify_orders;")
                existing_orders = {row[0] for row in cursor.fetchall()}

                print(f"📦 Órdenes ya existentes en DB: {len(existing_orders)}")

                # ======================================================
                # 2) Descargar órdenes desde Shopify
                # ======================================================
                url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/orders.json"
                headers = {
                    "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                    "Content-Type": "application/json"
                }
                params = {
                    "status": "any",
                    "fulfillment_status": "any",
                    "financial_status": "any",
                    "limit": 250
                }

                all_orders = []
                next_page = None

                while True:
                    response = (
                        requests.get(next_page, headers=headers)
                        if next_page
                        else requests.get(url, headers=headers, params=params)
                    )

                    response.raise_for_status()

                    data = response.json()
                    orders = data.get("orders", [])
                    all_orders.extend(orders)

                    link_header = response.headers.get("Link")
                    if link_header and 'rel="next"' in link_header:
                        next_page = link_header.split("<")[1].split(">")[0]
                    else:
                        break
                    
                if not all_orders:
                    print("✔ No se recibieron órdenes de Shopify.")
                    return None

                # ======================================================
                # 3) Normalizar
                # ======================================================
                df = pd.json_normalize(all_orders, max_level=2)

                # -------- Email robusto --------
                df["contact_email"] = (
                    df.get("contact_email")
                    .fillna(df.get("email"))
                    .fillna(df.get("customer.email"))
                )

                # -------- Descuentos --------
                df["discount_codes_flag"] = df.get("discount_codes", []).apply(
                    lambda x: bool(x) if isinstance(x, list) else False
                )

                df["discount_code"] = df.get("discount_codes", []).apply(
                    lambda x: x[0].get("code") if isinstance(x, list) and len(x) > 0 else None
                )

                # -------- Productos --------
                df["product_id"] = df.get("line_items", []).apply(
                    lambda x: x[0].get("product_id") if isinstance(x, list) and len(x) > 0 else None
                )

                df["product_name"] = df.get("line_items", []).apply(
                    lambda x: x[0].get("name") if isinstance(x, list) and len(x) > 0 else None
                )

                def extract_booking(properties):
                    if not isinstance(properties, list) or len(properties) < 2:
                        return None
                    try:
                        return f"{properties[0]['value']} {properties[1]['value']}"
                    except Exception:
                        return None

                df["booking"] = df.get("line_items", []).apply(
                    lambda x: extract_booking(x[0].get("properties")) if isinstance(x, list) and len(x) > 0 else None
                )

                df["vendor"] = df.get("line_items", []).apply(
                    lambda x: x[0].get("vendor") if isinstance(x, list) and len(x) > 0 else None
                )

                # -------- Dirección --------
                df["province"] = df.get("billing_address.province")
                df["country"] = df.get("billing_address.country")

                # ======================================================
                # 4) Columnas finales (defensivo)
                # ======================================================
                core_columns = [
                    "app_id",
                    "order_number",
                    "contact_email",
                    "created_at",
                    "currency",
                    "current_subtotal_price",
                    "current_total_price",
                    "current_total_discounts",
                    "customer_locale",
                    "discount_codes_flag",
                    "discount_code",
                    "total_discounts",
                    "processed_at",
                    "fulfillment_status",
                    "product_id",
                    "product_name",
                    "booking",
                    "vendor",
                    "province",
                    "country",
                ]

                df_final = df.reindex(columns=core_columns)

                # ======================================================
                # 5) Filtrar órdenes nuevas
                # ======================================================
                df_new = df_final[~df_final["order_number"].isin(existing_orders)]

                if df_new.empty:
                    print("✔ No hay nuevas órdenes para insertar.")
                    return None

                print(f"➕ Nuevas órdenes encontradas: {len(df_new)}")

                rows = [tuple(x) for x in df_new.to_numpy()]

                insert_query = f"""
                    INSERT INTO shopify_orders ({", ".join(core_columns)})
                    VALUES %s
                """

                execute_values(cursor, insert_query, rows)
                CONN.commit()

                print(f"✔ Insertadas {len(rows)} órdenes nuevas en shopify_orders")

                # ======================================================
                # 6️⃣ Devolver último discount_code
                # ======================================================
                return df_new.iloc[-1]["discount_code"]

            finally:
                cursor.close()
                CONN.close()


        def create_discount(self,body,):

            match = re.search(r'\+(\d+)', body)
            phone_number = "+" + match.group(1)
            
            return phone_number


        def get_latest_id_for_phone(self,  phone_number):
            CONN = create_conn()

            with CONN.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text
                    FROM discount_codes
                    WHERE phone_number = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (phone_number,)
                )
                row = cur.fetchone()
                return row[0] if row else None

        def confirm_discount_code(self, record_id):
            try:
                CONN = create_conn()

                cur = CONN.cursor()

                query = """
     UPDATE discount_codes
SET confirmed_payment = 'confirmed'
WHERE id = %s
RETURNING phone_number;
                """

                cur.execute(query, (record_id,))
                result = cur.fetchone()

                CONN.commit()
                cur.close()
                CONN.close()

                if result:
                    phone_number = result[0]
                    return phone_number
                else:
                    return None  # id no existe

            except Exception as e:
                print("❌ Error:", e)
                return None


        def generate_code(self, prefix="FREE100"):
            """Genera un código aleatorio tipo FREE100-AB32CD"""
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            return f"{prefix}-{random_part}"        

        def create_price_rule(self, title, usage_limit=1):
            url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/price_rules.json"
            headers = {
                "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            }       

            payload = {
                "price_rule": {
                    "title": title,
                    "target_type": "line_item",
                    "target_selection": "all",
                    "allocation_method": "across",   # <--- MUY IMPORTANTE
                    "value_type": "percentage",
                    "value": "-100.0",               # porcentajes NEGATIVOS
                    "customer_selection": "all",
                    "usage_limit": usage_limit,
                    "starts_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                }
            }       

            print("Creating price rule...")
            resp = requests.post(url, headers=headers, json=payload)
            print("STATUS:", resp.status_code)
            print("RESPONSE:", resp.text)
            resp.raise_for_status()
            return resp.json()["price_rule"]["id"]      




        def create_discount_code(self, price_rule_id: int, code: str):
            """Crea el código del descuento basado en la price rule."""
            payload = {
                "discount_code": {
                    "code": code
                }
            }       

            url = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}/price_rules/{price_rule_id}/discount_codes.json"
            resp = requests.post(url, json=payload, headers={
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json"
        })
            resp.raise_for_status()
            return resp.json()["discount_code"]["code"]     



        def make_100pct_discount(self, prefix="FREE100", usage_limit=1):
            code = PullShopify().generate_code(prefix)
            print("Creando price rule...")
            rule_id = PullShopify().create_price_rule(code, usage_limit)
            print("Creando discount code...")
            final_code = PullShopify().create_discount_code(rule_id, code)        

            return {
                "price_rule_id": rule_id,
                "discount_code": final_code
            }
        
        def update_discount_code_by_id(self, record_id, new_code):
            CONN = create_conn()

            try:
                with CONN:
                    with CONN.cursor() as cur:
                    
                        update_query = """
                            UPDATE discount_codes
                            SET code = %s
                            WHERE id = %s;
                        """

                        cur.execute(update_query, (new_code, record_id))

                        print(f"🔄 Código actualizado a '{new_code}' para el registro con ID {record_id}.")

            except Exception as e:
                print("❌ Error en update_discount_code_by_id:", e)

        def update_discount_code_by_id(self, record_id, new_code):
            CONN = create_conn()

            try:
                with CONN:
                    with CONN.cursor() as cur:

                        update_query = """
                            UPDATE discount_codes
                            SET code = %s
                            WHERE id = %s;
                        """

                        cur.execute(update_query, (new_code, record_id))

                        print(f"🔄 Código actualizado a '{new_code}' para el registro con ID {record_id}.")

            except Exception as e:
                print("❌ Error en update_discount_code_by_id:", e)



        def update_order_id_by_discount(self, discount_code):
            CONN = create_conn()

            try:
                with CONN:
                    with CONN.cursor() as cur:
                    
                        # 1️⃣ Buscar el ORDER ID más reciente en shopify_orders
                        select_order_query = """
                            SELECT id
                            FROM shopify_orders
                            WHERE discount_code = %s
                            ORDER BY created_at DESC
                            LIMIT 1;
                        """

                        cur.execute(select_order_query, (discount_code,))
                        order_row = cur.fetchone()

                        if not order_row:
                            print(f"⚠️ No se encontró ningún pedido con el código '{discount_code}'.")
                            return

                        order_id = order_row[0]
                        print(f"🔍 Order ID encontrado: {order_id}")

                        # 2️⃣ Buscar el registro MÁS RECIENTE en discount_codes con ese code
                        select_discount_query = """
                            SELECT id
                            FROM discount_codes
                            WHERE code = %s
                            ORDER BY created_at DESC
                            LIMIT 1;
                        """

                        cur.execute(select_discount_query, (discount_code,))
                        discount_row = cur.fetchone()

                        if not discount_row:
                            print(f"⚠️ No se encontró ningún registro en discount_codes con code='{discount_code}'.")
                            return

                        discount_record_id = discount_row[0]
                        print(f"🧾 Registro discount_codes encontrado: ID = {discount_record_id}")

                        # 3️⃣ Actualizar order_id, code_used_at y confirmed_payment
                        update_query = """
                            UPDATE discount_codes
                            SET 
                                order_id = %s,
                                code_used_at = NOW(),
                                confirmed_payment = 'confirmed'
                            WHERE id = %s;
                        """

                        cur.execute(update_query, (order_id, discount_record_id))

                        print(f"✅ order_id={order_id}, code_used_at y confirmed_payment='confirmed' guardados en discount_codes.id={discount_record_id}")

            except Exception as e:
                print("❌ Error en update_order_id_by_discount:", e)

        def insert_single_order_from_webhook(self, order_payload):
            """
            Inserta UNA orden de Shopify desde un webhook.
            Evita duplicados usando order_number.
            """

            from psycopg2.extras import execute_values
            from datetime import datetime

            CONN = create_conn()
            cursor = CONN.cursor()

            # -----------------------------
            # 1️⃣ Evitar duplicados
            # -----------------------------
            order_number = order_payload.get("order_number")

            cursor.execute(
                "SELECT 1 FROM shopify_orders WHERE order_number = %s;",
                (order_number,)
            )

            if cursor.fetchone():
                cursor.close()
                CONN.close()
                print(f"⚠ Orden {order_number} ya existe")
                return None

            # -----------------------------
            # 2️⃣ Extraer datos seguros
            # -----------------------------
            line_items = order_payload.get("line_items", [])
            first_item = line_items[0] if line_items else {}

            properties = first_item.get("properties", [])
            booking = None
            if isinstance(properties, list) and len(properties) >= 2:
                booking = f"{properties[0].get('value')} {properties[1].get('value')}"

            discount_codes = order_payload.get("discount_codes", [])
            discount_code = discount_codes[0]["code"] if discount_codes else None

            billing_address = order_payload.get("billing_address", {}) or {}

            contact_email = (
                order_payload.get("contact_email")
                or order_payload.get("email")
                or order_payload.get("customer", {}).get("email")
            )

            # -----------------------------
            # 3️⃣ Construir fila
            # -----------------------------
            row = (
                order_payload.get("app_id"),
                order_number,
                contact_email,
                order_payload.get("created_at"),
                order_payload.get("currency"),
                order_payload.get("current_subtotal_price"),
                order_payload.get("current_total_price"),
                order_payload.get("current_total_discounts"),
                order_payload.get("customer_locale"),
                bool(discount_codes),
                discount_code,
                order_payload.get("total_discounts"),
                order_payload.get("processed_at"),
                order_payload.get("fulfillment_status"),
                first_item.get("product_id"),
                first_item.get("name"),
                booking,
                first_item.get("vendor"),
                billing_address.get("province"),
                billing_address.get("country"),
            )

            # -----------------------------
            # 4️⃣ Insert
            # -----------------------------
            insert_sql = """
                INSERT INTO shopify_orders (
                    app_id,
                    order_number,
                    contact_email,
                    created_at,
                    currency,
                    current_subtotal_price,
                    current_total_price,
                    current_total_discounts,
                    customer_locale,
                    discount_codes_flag,
                    discount_code,
                    total_discounts,
                    processed_at,
                    fulfillment_status,
                    product_id,
                    product_name,
                    booking,
                    vendor,
                    province,
                    country
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(insert_sql, row)
            CONN.commit()

            cursor.close()
            CONN.close()

            print(f"✅ Orden {order_number} insertada correctamente")

            return discount_code

        def manage_user_language(self, phone_number, lang_selected=None):
                CONN = create_conn()
                current_lang = "undefined" 
                
                print(f"🛠️ DB DEBUG: Entrando a manage_user_language para {phone_number}. Selección: {lang_selected}")
        
                try:
                    cursor = CONN.cursor()
                    
                    # 1. Verificar usuario
                    check_query = "SELECT lang, step FROM chatbot_interaction WHERE phone_number = %s ORDER BY created_at DESC LIMIT 1;"
                    cursor.execute(check_query, (phone_number,))
                    row = cursor.fetchone()
        
                    if not row:
                        print("🆕 DB DEBUG: Usuario Nuevo. Insertando...")
                        # Insertamos step inicial como LANG
                        insert_query = "INSERT INTO chatbot_interaction (phone_number, lang, step, created_at) VALUES (%s, 'undefined', 'LANG', NOW());"
                        cursor.execute(insert_query, (phone_number,))
                        CONN.commit()
                        current_lang = "undefined"
                    else:
                        db_lang = row[0]
                        db_step = row[1]
                        
                        # SI EL USUARIO ELIGE UN IDIOMA VÁLIDO (1, 2 o 3)
                        if lang_selected and lang_selected in ["es", "en", "fr"]:
                            print(f"✏️ DB DEBUG: Actualizando a {lang_selected} y avanzando paso.")
                            
                            # 🔥 CAMBIO CLAVE: Actualizamos LANG y cambiamos STEP a 'WELCOME'
                            # para que el próximo mensaje ya no se interprete como selección de idioma.
                            update_query = """
                                UPDATE chatbot_interaction 
                                SET lang = %s, step = 'WELCOME' 
                                WHERE id = (SELECT id FROM chatbot_interaction WHERE phone_number = %s ORDER BY created_at DESC LIMIT 1);
                            """
                            cursor.execute(update_query, (lang_selected, phone_number))
                            CONN.commit()
                            current_lang = lang_selected
                        else:
                            # Si no está eligiendo idioma, mantenemos el que tiene
                            current_lang = db_lang
        
                    cursor.close()
                    CONN.close()
                    return current_lang
        
                except Exception as e:
                    print(f"❌ DB ERROR CRÍTICO: {e}")
                    if CONN: CONN.rollback()
                    return "es"