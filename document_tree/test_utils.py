from .validators import ENTITY_TYPE_MAP


def entity_type_for(instance) -> str:
    for entity_type, model in ENTITY_TYPE_MAP.items():
        if isinstance(instance, model):
            return entity_type
    raise ValueError(f'Unsupported entity type: {instance.__class__.__name__}')


def bind_entity_session(client, entity):
    session = client.session
    session['entity_type'] = entity_type_for(entity)
    session['entity_id'] = entity.pk
    session.save()
