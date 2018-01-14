from django.conf.urls import url

from . import views


urlpatterns = [

    url(r"^$", views.index, name="index"),

    # Registration
    url(r"^register/$", views.register, name="register"),
    url(r"^school/$", views.schools, name="school"),
    url(r"^inactive/$", views.inactive, name="inactive"),

    # Team editing
    url(r"^teams/$", views.display_teams, name="teams"),
    url(r"^teams/edit/(\d+)?$", views.edit_team, name="edit_team"),
    url(r"^teams/remove/(\d+)$", views.remove_team, name="remove_team"),

]
