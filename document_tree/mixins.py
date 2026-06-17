from rest_framework.exceptions import NotAuthenticated


class EntityContextMixin:
    def get_request_entity(self):
        entity = getattr(self.request, 'entity', None)
        if entity is None:
            raise NotAuthenticated('No active entity in session')
        return entity
