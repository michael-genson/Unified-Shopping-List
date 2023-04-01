class Routes:
    FOODS = "/api/foods"

    GROUPS_EVENTS_NOTIFICATIONS = "/api/groups/events/notifications"
    GROUPS_EVENTS_NOTIFICATIONS_NOTIFICATION_ID = (
        lambda notification_id: f"{Routes.GROUPS_EVENTS_NOTIFICATIONS}/{notification_id}"
    )

    GROUPS_LABELS = "/api/groups/labels"

    GROUPS_SHOPPING_LISTS = "/api/groups/shopping/lists"
    GROUPS_SHOPPING_LISTS_SHOPPING_LIST_ID = lambda list_id: f"{Routes.GROUPS_SHOPPING_LISTS}/{list_id}"
    GROUPS_SHOPPING_LISTS_SHOPPING_LIST_ID_RECIPE_RECIPE_ID_DELETE = (
        lambda list_id, recipe_id: f"{Routes.GROUPS_SHOPPING_LISTS}/{list_id}/recipe/{recipe_id}/delete"
    )
    GROUPS_SHOPPING_ITEMS = "/api/groups/shopping/items"
    GROUPS_SHOPPING_ITEMS_CREATE_BULK = "/api/groups/shopping/items/create-bulk"
    GROUPS_SHOPPING_ITEMS_ITEM_ID = lambda item_id: f"{Routes.GROUPS_SHOPPING_ITEMS}/{item_id}"

    RECIPES = "/api/recipes"

    USERS_SELF = "/api/users/self"
    USERS_API_TOKENS = "/api/users/api-tokens"
    USERS_API_TOKENS_TOKEN_ID = lambda token_id: f"{Routes.USERS_API_TOKENS}/{token_id}"
