from rest_framework import serializers

from .models import Groupement, Laboratory, Pharmacy


class LaboratorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Laboratory
        fields = ('id', 'name', 'code')


class GroupementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Groupement
        fields = ('id', 'name')


class PharmacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = ('id', 'name', 'groupement_id')
