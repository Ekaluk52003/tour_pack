def user_group_flags(request):
    if request.user.is_authenticated:
        return {
            'is_owner': request.user.groups.filter(name='owner').exists(),
        }
    return {'is_owner': False}
