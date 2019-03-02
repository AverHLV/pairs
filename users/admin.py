from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Note


def make_email_checked(_, __, queryset):
    queryset.update(email_checked=True)


def mark_as_moderator(_, __, queryset):
    queryset.update(is_moderator=True)


def mark_as_ordinary_user(_, __, queryset):
    queryset.update(is_moderator=False)


def set_level0(_, __, queryset):
    queryset.update(profit_level=0)


def set_level1(_, __, queryset):
    queryset.update(profit_level=1)


def set_level2(_, __, queryset):
    queryset.update(profit_level=2)


make_email_checked.short_description = 'Mark selected users emails as checked'
mark_as_moderator.short_description = 'Mark selected users as moderators'
mark_as_ordinary_user.short_description = 'Delete moderator`s permissions in selected users'
set_level0.short_description = 'Set profit level to 0 (lowest)'
set_level1.short_description = 'Set profit level to 1'
set_level2.short_description = 'Set profit level to 2 (highest)'


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = 'username', 'email_checked', 'is_moderator', 'pairs_count', 'profit_level', 'profit'
    search_fields = 'username',
    ordering = '-date_joined',
    actions = make_email_checked, mark_as_moderator, mark_as_ordinary_user, set_level0, set_level1, set_level2


CustomUserAdmin.fieldsets += ('CustomUser fields', {'fields': ('pairs_count', 'profit_level', 'profit')}),


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    model = Note
    readonly_fields = 'created',
    search_fields = 'text',
    ordering = '-created',

    def get_search_results(self, request, queryset, search_term):
        """ Search by author username """

        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        try:
            queryset |= self.model.objects.filter(author=CustomUser.objects.get(username=search_term))

        finally:
            return queryset, use_distinct
