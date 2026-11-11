"use client";

import { OtpCodeFields } from "@/components/OtpCodeFields";

type Props = {
  phone: string;
  required: boolean;
  code: string;
  onCodeChange: (value: string) => void;
  onTicket: (ticket: string) => void;
  send: (phone: string) => Promise<{ ticket: string; retry_after: number }>;
  disabled?: boolean;
};

export function WhatsAppOtpFields({ phone, required, code, onCodeChange, onTicket, send, disabled }: Props) {
  return (
    <OtpCodeFields
      target={phone}
      required={required}
      canSend={phone.replace(/\D/g, "").length >= 10}
      hint="Enviaremos um código no WhatsApp deste número. O número precisa ter WhatsApp ativo."
      sendLabel="Enviar código no WhatsApp"
      resendLabel="Reenviar código no WhatsApp"
      codeLabel="Código do WhatsApp"
      code={code}
      onCodeChange={onCodeChange}
      onTicket={onTicket}
      send={send}
      disabled={disabled}
    />
  );
}
