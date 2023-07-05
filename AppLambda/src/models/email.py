from email.message import EmailMessage

from fastapi.templating import Jinja2Templates

from ..app import secrets, settings

email_templates = Jinja2Templates(directory="./src/static/email_templates")


class GenericEmailTemplate:
    def __init__(self, template: str, is_html: bool = False) -> None:
        self.template = template
        self.is_html = is_html

    def message(
        self,
        subject: str,
        sender: str,
        recipients: str | list[str],
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        **kwargs,
    ) -> EmailMessage:
        """Constructs a message to be sent via SMTP. Provide merge fields as kwargs"""

        body_template = email_templates.get_template(self.template)
        body = body_template.render(**kwargs)

        if isinstance(recipients, list):
            recipients = ", ".join(recipients)

        if isinstance(cc, list):
            cc = ", ".join(cc)

        if isinstance(bcc, list):
            bcc = ", ".join(bcc)

        msg = EmailMessage()
        if self.is_html:
            msg.set_content(body, subtype="html")

        else:
            msg.set_content(body)

        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipients
        msg["Cc"] = cc or ""
        msg["Bcc"] = bcc or ""

        return msg


class RegistrationEmail:
    def __init__(self) -> None:
        self.template = GenericEmailTemplate("registration.html", is_html=True)

    def message(
        self,
        recipient_username: str,
        recipient_email: str,
        registration_url: str,
    ) -> EmailMessage:
        subject = f"Confirm your email for {settings.app_title}"
        return self.template.message(
            subject,
            sender=secrets.smtp_sender,
            recipients=recipient_email,
            name=recipient_username,
            registration_url=registration_url,
        )


class PasswordResetEmail:
    def __init__(self) -> None:
        self.template = GenericEmailTemplate("password_reset.html", is_html=True)

    def message(
        self,
        recipient_username: str,
        recipient_email: str,
        password_reset_url: str,
    ) -> EmailMessage:
        subject = f"Reset your password for {settings.app_title}"
        return self.template.message(
            subject,
            sender=secrets.smtp_sender,
            recipients=recipient_email,
            name=recipient_username,
            password_reset_url=password_reset_url,
        )
