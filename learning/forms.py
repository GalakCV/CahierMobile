from django import forms

from content.models import Chapter, Competency, ContentIssue, GrammarTopic, VocabularyTopic

from .models import StudySession, UserSetting


def topic_choices():
    groups = [("", "Todos os temas")]
    g = [(f"g:{t.pk}", f"{t.chapter.number}. {t.title}") for t in
         GrammarTopic.objects.filter(is_active=True, chapter__is_active=True).select_related("chapter")]
    v = [(f"v:{t.pk}", f"{t.chapter.number}. {t.title}") for t in
         VocabularyTopic.objects.filter(is_active=True, chapter__is_active=True).select_related("chapter")]
    if g:
        groups.append(("Gramática", g))
    if v:
        groups.append(("Vocabulário", v))
    return groups


class SessionForm(forms.Form):
    chapter = forms.ModelChoiceField(
        label="Capítulo", required=False, empty_label="Todos os capítulos",
        queryset=Chapter.objects.filter(is_active=True, is_planned=False).order_by("number"))
    topic = forms.ChoiceField(label="Tema", required=False)
    competency = forms.ModelChoiceField(label="Competência", required=False, empty_label="Todas",
                                        queryset=Competency.objects.all())
    difficulties = forms.TypedMultipleChoiceField(
        label="Dificuldade", required=False, coerce=int,
        choices=[(1, "1 · reconhecimento"), (2, "2 · aplicação guiada"), (3, "3 · em contexto"),
                 (4, "4 · combinação"), (5, "5 · menos apoio")],
        widget=forms.CheckboxSelectMultiple)
    count = forms.IntegerField(label="Quantidade de questões", min_value=3, max_value=50)
    mode = forms.ChoiceField(label="Modo", choices=StudySession.Mode.choices, widget=forms.RadioSelect,
                             initial=StudySession.Mode.PRACTICE)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].choices = topic_choices()
        if not self.is_bound:
            self.fields["count"].initial = UserSetting.get().default_session_size


class IssueForm(forms.ModelForm):
    class Meta:
        model = ContentIssue
        fields = ["kind", "comment"]
        labels = {"kind": "O que há de errado?", "comment": "Detalhes (opcional)"}
        widgets = {"kind": forms.RadioSelect, "comment": forms.Textarea(attrs={"rows": 4, "maxlength": 2000})}


class SettingsForm(forms.ModelForm):
    class Meta:
        model = UserSetting
        fields = ["display_name", "current_chapter", "default_session_size", "daily_goal_minutes",
                  "show_keyboard", "font_size", "theme"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["current_chapter"].queryset = Chapter.objects.filter(is_active=True, is_planned=False)
        self.fields["current_chapter"].empty_label = "Automático (último estudado)"
