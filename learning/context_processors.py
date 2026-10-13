from django.db.utils import DatabaseError
from django.utils import timezone

from .models import ReviewItem, UserSetting


def study_context(request):
    """Dados leves usados em todas as páginas (preferências e contagem de revisões)."""
    try:
        setting = UserSetting.get()
        due = ReviewItem.objects.filter(due_at__lte=timezone.now(), exercise__is_active=True).count()
    except DatabaseError:  # banco ainda não migrado
        return {}
    return {"user_setting": setting, "due_reviews_count": due}
