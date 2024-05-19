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
        pilot.role = Pilot.Role.STAFF
        pilot.save()
        return pilot


def validate_phone(phone):
    for character in phone:
        if character not in "0123456789+() ":
            raise ValidationError(
                f"{phone} ist keine Telefonnummer.", params={"phone": phone}
            )


class Pilot(AbstractBaseUser):
    Role = models.IntegerChoices("Role", "GUEST MEMBER ORGA STAFF")

    email = models.EmailField(max_length=255, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, validators=[validate_phone])
    date_joined = models.DateTimeField(auto_now_add=True)
    role = models.IntegerField(choices=Role.choices, default=Role.GUEST)
    prepaid_flights = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(0)], default=0
    )
    is_new = models.BooleanField(default=True)
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
        self.role = self.Role.MEMBER
        self.save()

    @property
    def is_member(self):
        return self.role >= self.Role.MEMBER

    @property
    def is_orga(self):
        return self.role >= self.Role.ORGA

    @property
    def is_staff(self):
        return self.role == self.Role.STAFF

    @property
    def short_name(self):
        MAX_LENGTH = 15
        if len(name := str(self)) <= MAX_LENGTH:
            return name

        first, *middle_names, last = name.split()
        for i, name in enumerate(middle_names):
            if name in ["von", "Von"]:
                middle_names[i] = "v."
        
        short_name = " ".join([first] + middle_names + [last])
        if len(short_name) <= MAX_LENGTH:
            return short_name
        
        short_name = short_name[:MAX_LENGTH - 1] + "."
        if short_name.endswith("-."):
            return short_name[:-2] + "."

        if short_name.endswith(" ."):
            return short_name[:-2]

        return short_name

    @property
    def day_passes_of_this_season(self):
        signups_of_this_season = (
            self.signups.filter(**{"training__date__gte": f"{now().year}-1-1"})
            .select_related("training")
            .prefetch_related("purchases")
        )
        purchases = [
            purchase
            for signup in signups_of_this_season
            for purchase in signup.purchases.all()
        ]
        return [purchase for purchase in purchases if purchase.is_day_pass]

    @property
    def has_bills(self):
        signups = self.signups.prefetch_related("bill")
        return any(signup.is_paid for signup in signups)
