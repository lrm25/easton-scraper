from django.contrib import admin
from .models import EastonClass


# Register your models here.
class EastonClassAdmin(admin.ModelAdmin):
    pass


admin.site.register(EastonClass, EastonClassAdmin)
