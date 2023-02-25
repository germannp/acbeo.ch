from django.conf import settings
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.timezone import now


class Post(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts"
    )
    content = models.TextField()
    created_on = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-created_on"]

    def __str__(self):
        return self.title


class PilotManager(BaseUserManager):
    def create_user(self, email, password=None):
        if not email:
            raise ValueError("Pilot must have an email address")

        pilot = self.model(email=self.normalize_email(email))

        pilot.set_password(password)
        pilot.save()
        return pilot

    def create_superuser(self, email, password=None):
        pilot = self.create_user(
            email,
            password=password,
        )
        pilot.role = Pilot.Role.Staff
        pilot.save()
        return pilot


def validate_phone(phone):
    for character in phone:
        if character not in "0123456789+() ":
            raise ValidationError(
                f"{phone} ist keine Telefonnummer.", params={"phone": phone}
            )


class Pilot(AbstractBaseUser):
    Role = models.IntegerChoices("Role", "Guest Member Orga Staff")

    email = models.EmailField(max_length=255, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, validators=[validate_phone])
    date_joined = models.DateTimeField(auto_now_add=True)
    role = models.IntegerField(choices=Role.choices, default=Role.Guest)
    prepaid_flights = models.SmallIntegerField(
        validators=[MinValueValidator(0)], default=0
    )
    is_active = models.BooleanField(default=True)

    objects = PilotManager()

    USERNAME_FIELD = "email"

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.first_name + " " + self.last_name

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True

    def make_member(self):
        self.role = self.Role.Member
        self.save()

    @property
    def is_member(self):
        return self.role >= self.Role.Member

    @property
    def is_orga(self):
        return self.role >= self.Role.Orga

    @property
    def is_staff(self):
        return self.role == self.Role.Staff
