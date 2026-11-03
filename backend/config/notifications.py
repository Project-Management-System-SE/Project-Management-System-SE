from tasks.models import UserNotification


def create_notifications(title, message, recipients):
    unique_recipients = {}
    for recipient in recipients:
        if recipient:
            unique_recipients.setdefault(recipient.pk, recipient)

    return UserNotification.objects.bulk_create(
        [
            UserNotification(
                recipient=recipient,
                title=title,
                message=message,
            )
            for recipient in unique_recipients.values()
        ]
    )
