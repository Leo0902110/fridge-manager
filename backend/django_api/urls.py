"""API urls for Django migration."""

from django.urls import path

from .views_auth import login_view, logout_view, me_view
from .views_foods import (
	complete_food,
	delete_food,
	delete_food_event,
	food_detail,
	food_item_dispatch,
	foods_collection,
	list_foods,
	overview,
	shelf_life_reference,
	today_recipe,
	update_food,
	upload_image,
)
from .views_recognition import categories, eating_suggestion, infer_shelf_life, recognize_by_name, recognize_image
from .views_reminders import check_expiry, history, mark_sent, pending, send_template, strategy


urlpatterns = [
	path("auth/login", login_view),
	path("auth/me", me_view),
	path("auth/logout", logout_view),

	path("foods", foods_collection),
	path("foods/recipe/today", today_recipe),
	path("foods/upload-image", upload_image),
	path("foods/stats/overview", overview),
	path("foods/reference/shelf-life", shelf_life_reference),
	path("foods/events/<int:event_id>", delete_food_event),
	path("foods/<int:food_id>", food_item_dispatch),
	path("foods/<int:food_id>/complete", complete_food),

	path("recognition/image", recognize_image),
	path("recognition/infer-shelf-life", infer_shelf_life),
	path("recognition/name", recognize_by_name),
	path("recognition/suggestion/<str:food_name>", eating_suggestion),
	path("recognition/categories", categories),

	path("reminders/pending", pending),
	path("reminders/check-expiry", check_expiry),
	path("reminders/strategy", strategy),
	path("reminders/<int:reminder_id>/send", mark_sent),
	path("reminders/history", history),
	path("reminders/wechat/template", send_template),
]