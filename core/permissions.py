from flask_login import current_user



def is_admin():
    return current_user.role == "ADMIN"


def is_manager():
    return current_user.role in ["ADMIN", "MANAGER"]


def is_central_user(user=None):
    user = user or current_user
    return bool(user.sector and user.sector.is_central)


def can_access_sector(conversation):
    """
    ADMIN pode tudo.
    Outros só podem acessar se for do mesmo setor.
    """
    if is_admin():
        return True

    return conversation.current_sector_id == current_user.sector_id


def can_open_conversation(conversation):
    """
    Mantém exatamente a regra atual do sistema:
    - ADMIN pode tudo
    - Outros:
        - Só mesmo setor
        - Não pode abrir se estiver assumida por outro
    """
    if is_admin():
        return True, None

    if conversation.current_sector_id != current_user.sector_id:
        return False, "Sem permissão"

    if conversation.assigned_to and conversation.assigned_to != current_user.id:
        return False, "Já assumida"

    return True, None


def can_move_conversation(conversation):
    

    # ADMIN pode tudo
    if is_admin():
        return True

    # AGENT pode mover apenas se:
    # - estiver atribuída a ele
    # - e a conversa estiver no setor dele
    if (
        conversation.assigned_to == current_user.id and
        conversation.current_sector_id == current_user.sector_id
    ):
        return True

    return False


def can_assign_conversation(conversation):

    # ADMIN pode tudo
    if is_admin():
        return True

    # CENTRAL pode assumir qualquer conversa
    if is_central_user():
        return True

    # permitir assumir conversas sem setor
    if conversation.current_sector_id is None:
        return True

    # setor assume apenas o próprio
    return conversation.current_sector_id == current_user.sector_id
