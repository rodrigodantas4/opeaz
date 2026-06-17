from django.contrib import admin

from .models import (
    CommercialCondition,
    Document,
    Flyer,
    Groupement,
    Laboratory,
    Pharmacy,
)

admin.site.register(Groupement)
admin.site.register(Pharmacy)
admin.site.register(Laboratory)
admin.site.register(Document)
admin.site.register(Flyer)
admin.site.register(CommercialCondition)
