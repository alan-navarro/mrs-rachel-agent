class CustomerPayload:
    """
    Limpia y organiza los datos del payload recibido de Twilio WhatsApp.
    """

    def __init__(self, payload: dict):
        self.raw = payload  # Guarda el payload completo por si lo necesitas después

        # Extraer campos directamente del payload de Twilio
        self.account_sid = payload.get("AccountSid")
        self.message_sid = payload.get("MessageSid")
        self.profile_name = payload.get("ProfileName")
        self.body = payload.get("Body")
        self.from_number = self._extract_number(payload.get("From"))
        self.to_number = self._extract_number(payload.get("To"))
        self.message_type = payload.get("MessageType", "text")
        self.wa_id = payload.get("WaId")

    def _extract_number(self, raw_value):
        """
        Limpia el número, eliminando el prefijo 'whatsapp:+' o 'whatsapp:'.
        """
        if not raw_value:
            return None
        return raw_value.replace("whatsapp:+", "").replace("whatsapp:", "")

    def __str__(self):
        """
        Representación legible de los campos más importantes.
        """
        return (
            f"From: {self.from_number}, To: {self.to_number}, "
            f"Profile: {self.profile_name}, Message: {self.body}"
        )

    def to_dict(self):
        """
        Devuelve los datos estructurados como diccionario limpio.
        """
        return {
            "account_sid": self.account_sid,
            "message_sid": self.message_sid,
            "profile_name": self.profile_name,
            "message": self.body,
            "from_number": self.from_number,
            "to_number": self.to_number,
            "message_type": self.message_type,
            "wa_id": self.wa_id
        }
