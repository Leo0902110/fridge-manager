"""Django ORM models mapped to existing SQLite tables."""

from django.db import models


class WeChatUser(models.Model):
    openid = models.CharField(max_length=255, unique=True)
    unionid = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users"
        managed = False

    @property
    def is_authenticated(self) -> bool:
        return True


class UserSession(models.Model):
    token = models.CharField(max_length=255, primary_key=True)
    user = models.ForeignKey(WeChatUser, on_delete=models.CASCADE, db_column="user_id", related_name="sessions")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_sessions"
        managed = False


class Food(models.Model):
    user = models.ForeignKey(WeChatUser, on_delete=models.CASCADE, db_column="user_id", null=True, blank=True, related_name="foods")
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, null=True, blank=True)
    image_url = models.TextField(null=True, blank=True)
    put_date = models.DateField()
    expiry_date = models.DateField()
    shelf_life_days = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, default="fresh")
    location = models.CharField(max_length=32, default="fridge")
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "foods"
        managed = False


class FoodEvent(models.Model):
    user = models.ForeignKey(WeChatUser, on_delete=models.CASCADE, db_column="user_id", null=True, blank=True, related_name="food_events")
    food_id = models.IntegerField(null=True, blank=True)
    event_type = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, null=True, blank=True)
    image_url = models.TextField(null=True, blank=True)
    put_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    shelf_life_days = models.IntegerField(null=True, blank=True)
    location = models.CharField(max_length=32, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "food_events"
        managed = False


class Reminder(models.Model):
    food = models.ForeignKey(Food, on_delete=models.CASCADE, db_column="food_id", related_name="reminders")
    user_id = models.CharField(max_length=255, null=True, blank=True)
    remind_date = models.DateField()
    message = models.TextField(null=True, blank=True)
    is_sent = models.IntegerField(default=0)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reminders"
        managed = False


class ShelfLifeReference(models.Model):
    food_name = models.CharField(max_length=255, unique=True)
    category = models.CharField(max_length=255, null=True, blank=True)
    fridge_days = models.IntegerField(default=0)
    freezer_days = models.IntegerField(default=0)
    room_temp_days = models.IntegerField(default=0)
    recommended_location = models.CharField(max_length=32, default="fridge")
    storage_tip = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "shelf_life_reference"
        managed = False