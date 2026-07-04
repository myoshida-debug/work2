from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class RestoreMetadata(models.Model):
    STATUS_CHOICES = [
        ('draft', '作成済み'),
        ('sent_to_dmz', 'DMZ送信済み'),
        ('imported_to_open', 'OpenSide取込済み'),
        ('returned_to_dmz', '返却DMZ送信済み'),
        ('imported_to_close', 'CloseSide取込済み'),
    ]

    source_id = models.CharField(max_length=255, unique=True)
    template_type = models.CharField(max_length=255)
    restore_map = models.JSONField()
    prompt_json = models.JSONField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.source_id} ({self.template_type})'


class RestoredResult(models.Model):
    STATUS_CHOICES = [
        ('imported', '取込済み'),
        ('deleted', '削除済み'),
    ]

    source_id = models.CharField(max_length=255, db_index=True)
    result_id = models.CharField(max_length=255, blank=True, default='')
    template_type = models.CharField(max_length=255, blank=True, default='')
    result_text = models.TextField()
    restored_text = models.TextField()
    result_json = models.JSONField(null=True, blank=True)
    imported_filename = models.CharField(max_length=255, blank=True, default='')
    reviewer = models.CharField(max_length=255, blank=True, default='')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='imported')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.result_id or self.source_id} ({self.template_type})'


class PersonNameMixin(models.Model):
    class Meta:
        abstract = True

    @property
    def full_name(self) -> str:
        return f'{self.surname}{self.given_name}'.strip()

    @property
    def kana_full_name(self) -> str:
        return f'{self.kana_surname}{self.kana_given_name}'.strip()

    def name_variants(self) -> list[str]:
        variants: list[str] = []
        for candidate in (
            self.full_name,
            f'{self.surname} {self.given_name}'.strip(),
            f'{self.surname}　{self.given_name}'.strip(),
            self.kana_full_name,
            f'{self.kana_surname} {self.kana_given_name}'.strip(),
            f'{self.kana_surname}　{self.kana_given_name}'.strip(),
        ):
            if candidate and candidate not in variants:
                variants.append(candidate)
        return variants


class Patient(PersonNameMixin):
    SEX_CHOICES = [
        ('male', '男'),
        ('female', '女'),
        ('other', 'その他'),
        ('unknown', '不明'),
    ]

    patient_id = models.CharField(max_length=255, unique=True, db_index=True)
    surname = models.CharField(max_length=255, blank=True, default='')
    given_name = models.CharField(max_length=255, blank=True, default='')
    kana_surname = models.CharField(max_length=255, blank=True, default='')
    kana_given_name = models.CharField(max_length=255, blank=True, default='')
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=16, blank=True, default='', choices=SEX_CHOICES)
    primary_diagnosis = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['patient_id']

    def __str__(self):
        return f'{self.patient_id} {self.full_name}'.strip()


class Staff(PersonNameMixin):
    staff_id = models.CharField(max_length=255, unique=True, db_index=True)
    surname = models.CharField(max_length=255, blank=True, default='')
    given_name = models.CharField(max_length=255, blank=True, default='')
    kana_surname = models.CharField(max_length=255, blank=True, default='')
    kana_given_name = models.CharField(max_length=255, blank=True, default='')
    role_label = models.CharField(max_length=255, blank=True, default='職員')
    occupation_label = models.CharField(max_length=255, blank=True, default='')
    position_label = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['staff_id']

    def __str__(self):
        return f'{self.staff_id} {self.full_name} {self.display_role_label}'.strip()

    def save(self, *args, **kwargs):
        self.role_label = self.occupation_label or self.position_label or self.role_label or '職員'
        super().save(*args, **kwargs)

    @property
    def anonymization_label_prefix(self) -> str:
        return (self.occupation_label or self.role_label or self.position_label or '職員').strip() or '職員'

    @property
    def display_role_label(self) -> str:
        parts = [part.strip() for part in (self.occupation_label, self.position_label) if str(part or '').strip()]
        if parts:
            return ' / '.join(parts)
        return (self.role_label or '職員').strip() or '職員'


class PatientLinkedPersonMixin(PersonNameMixin):
    class Meta:
        abstract = True

    RELATION_KIND_CHOICES = [
        ('family', '家族'),
        ('guardian', '後見人'),
    ]
    LINKED_PERSON_CODE_PREFIX = 'LP'

    patient_id = models.CharField(max_length=255, db_index=True)
    branch_no = models.PositiveIntegerField(verbose_name='枝番', db_index=True)
    linked_person_code = models.CharField(
        verbose_name='個別コード',
        max_length=16,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        editable=False,
    )
    relation_kind = models.CharField(max_length=16, verbose_name='種別', choices=RELATION_KIND_CHOICES, default='family', db_index=True)
    surname = models.CharField(max_length=255, blank=True, default='')
    given_name = models.CharField(max_length=255, blank=True, default='')
    kana_surname = models.CharField(max_length=255, blank=True, default='')
    kana_given_name = models.CharField(max_length=255, blank=True, default='')
    relationship_label = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.relation_kind = str(self.relation_kind or 'family').strip() or 'family'
        self.relationship_label = str(self.relationship_label or '').strip()
        with transaction.atomic():
            super().save(*args, **kwargs)
            expected_code = self.build_linked_person_code(self.pk)
            if expected_code and self.linked_person_code != expected_code:
                type(self).objects.filter(pk=self.pk).update(linked_person_code=expected_code)
                self.linked_person_code = expected_code

    @classmethod
    def build_linked_person_code(cls, pk: int | None) -> str:
        if not pk:
            return ''
        return f'{cls.LINKED_PERSON_CODE_PREFIX}{int(pk):08d}'

    @property
    def branch_display_label(self) -> str:
        patient_id = str(self.patient_id or '').strip()
        branch_no = self.branch_no
        if patient_id and branch_no:
            return f'{patient_id}-{branch_no}'
        if branch_no:
            return str(branch_no)
        return patient_id

    @property
    def linked_person_display_label(self) -> str:
        code = str(self.linked_person_code or '').strip()
        branch = self.branch_display_label
        if code and branch and code != branch:
            return f'{code} ({branch})'
        return code or branch

    @property
    def anonymization_label_prefix(self) -> str:
        relationship = str(self.relationship_label or '').strip()
        relation_kind = str(self.relation_kind or '').strip()
        if relation_kind == 'guardian':
            return relationship or '後見人'
        if relationship:
            return f'家族（{relationship}）'
        return '家族'

    @property
    def patient_label(self) -> str:
        return str(self.patient_id or '').strip()

    @property
    def relation_kind_label(self) -> str:
        relation_kind = str(self.relation_kind or '').strip()
        if relation_kind == 'guardian':
            return '後見人'
        return '家族'

    @property
    def relationship_display_label(self) -> str:
        return str(self.relationship_label or '').strip()


class PatientLinkedPerson(PatientLinkedPersonMixin):
    class Meta:
        ordering = ['patient_id', 'branch_no']
        constraints = [
            models.UniqueConstraint(fields=['patient_id', 'branch_no'], name='unique_patient_linked_person_branch_no'),
        ]

    def __str__(self):
        return f'{self.linked_person_display_label} {self.full_name} {self.relation_kind_label} {self.relationship_display_label}'.strip()


# Backward-compatible aliases for older imports.
PatientFamily = PatientLinkedPerson
Guardian = PatientLinkedPerson


class Prompt(models.Model):
    STATUS_CHOICES = [
        ('draft', '作成済み'),
        ('sent_to_dmz', 'DMZ送信済み'),
        ('imported_to_open', 'OpenSide取込済み'),
    ]

    name = models.CharField(max_length=255)
    content = models.TextField()
    source_input_data = models.JSONField(blank=True, default=dict)
    source_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# テンプレート用の定義（フォームと合わせてください）
TEMPLATE_CHOICES = [
    ('入院時サマリー', '入院時サマリー'),
    ('精神科入院時サマリー', '精神科入院時サマリー'),
    ('精神科退院時サマリー（医師用）', '精神科退院時サマリー（医師用）'),
    ('看護入院時サマリー', '看護入院時サマリー'),
    ('看護中間サマリー', '看護中間サマリー'),
    ('看護退院時サマリー', '看護退院時サマリー'),
    ('OT評価サマリー', 'OT評価サマリー'),
    ('PSW退院支援サマリー', 'PSW退院支援サマリー'),
    ('精神科訪問看護サマリー', '精神科訪問看護サマリー'),
    ('退院時サマリー', '退院時サマリー'),
    ('中間サマリー', '中間サマリー'),
    ('インシデントレポート', 'インシデントレポート'),
    ('委員会議事録', '委員会議事録'),
    ('看護計画', '看護計画'),
]


class Template(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    source_filename = models.CharField(max_length=255, blank=True, default='')
    content = models.TextField()
    basic_content = models.TextField(blank=True, default='')
    additional_content = models.TextField(blank=True, default='')
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'template_type', 'name', 'id']

    def __str__(self):
        return f"{self.template_type} - {self.name}"

    @property
    def combined_content(self):
        if self.additional_content:
            return f"{self.basic_content}\n\n{self.additional_content}"
        return self.basic_content or self.content


class TemplateInputDefault(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    field_key = models.CharField(max_length=255)
    default_text = models.TextField(blank=True, default='')
    required_override = models.BooleanField(null=True, blank=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['template_type', 'field_key'], name='unique_template_input_default'),
        ]
        ordering = ['template_type', 'field_key']

    def __str__(self):
        return f'{self.template_type}:{self.field_key}'


FIELD_INPUT_TYPE_CHOICES = [
    ('textarea', 'テキスト'),
    ('date', '日付'),
    ('checkbox_group', 'チェックボックス'),
]


class TemplateInputField(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    field_key = models.CharField(max_length=255)
    label = models.CharField(max_length=255, blank=True, default='')
    input_type = models.CharField(max_length=32, choices=FIELD_INPUT_TYPE_CHOICES, default='textarea')
    section_title = models.CharField(max_length=255, blank=True, default='')
    required = models.BooleanField(default=False)
    allow_other = models.BooleanField(default=True)
    other_label = models.CharField(max_length=255, blank=True, default='その他')
    other_placeholder = models.CharField(max_length=255, blank=True, default='自由入力')
    help_text = models.TextField(blank=True, default='')
    textarea_rows = models.PositiveIntegerField(default=3)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['template_type', 'field_key'], name='unique_template_input_field'),
        ]
        ordering = ['template_type', 'sort_order', 'field_key']

    def __str__(self):
        return f'{self.template_type}:{self.field_key}'


class TemplateInputCheckboxGroup(models.Model):
    template_type = models.CharField(max_length=255, choices=TEMPLATE_CHOICES)
    field_key = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['template_type', 'field_key'], name='unique_template_input_checkbox_group'),
        ]
        ordering = ['template_type', 'field_key']

    def __str__(self):
        return f'{self.template_type}:{self.field_key}'


class TemplateInputCheckboxOption(models.Model):
    group = models.ForeignKey(TemplateInputCheckboxGroup, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['group', 'text'], name='unique_template_input_checkbox_option'),
        ]
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.group.template_type}:{self.group.field_key}:{self.text}'


class AnonymizationRule(models.Model):
    """Store editable anonymization rule text for admin editing and runtime display."""
    name = models.CharField(max_length=255, default='default')
    content = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class OperationLog(models.Model):
    RESULT_CHOICES = [
        ('success', '成功'),
        ('failure', '失敗'),
    ]

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor_username = models.CharField(max_length=150, blank=True, default='')
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80, blank=True, default='')
    target_id = models.CharField(max_length=255, blank=True, default='')
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    import_source_ip = models.GenericIPAddressField(null=True, blank=True)
    result = models.CharField(max_length=16, choices=RESULT_CHOICES, default='success')
    error_message = models.TextField(blank=True, default='')
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M:%S} {self.action} {self.target_id} {self.result}'
