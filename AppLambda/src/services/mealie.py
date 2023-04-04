from functools import cache, cached_property
from typing import Iterable, Optional, TypeVar, cast

from fuzzywuzzy import process

from ..clients.mealie import MealieClient
from ..models.account_linking import NotLinkedError, UserMealieConfiguration
from ..models.core import User
from ..models.mealie import (
    Food,
    Label,
    MealieRecipe,
    MealieShoppingListItemCreate,
    MealieShoppingListItemExtras,
    MealieShoppingListItemOut,
    MealieShoppingListItemsCollectionOut,
    MealieShoppingListItemUpdateBulk,
    MealieShoppingListOut,
)

SHOPPING_LIST_ITEM = TypeVar("SHOPPING_LIST_ITEM", bound=MealieShoppingListItemCreate)


class MealieListService:
    """Manages Mealie list and list item interactions"""

    def __init__(self, user: User) -> None:
        if not user.is_linked_to_mealie:
            raise NotLinkedError(user.username, "mealie")

        self.config = cast(UserMealieConfiguration, user.configuration.mealie)
        self._client = MealieClient(self.config.base_url, self.config.auth_token)

        self.list_items_by_list_id: dict[str, list[MealieShoppingListItemOut]] = {}
        """
        map of {shopping_list_id: list[shopping_list_items]}
        
        *not guaranteed to store checked items*
        """

    @cached_property
    def recipe_store(self) -> dict[str, MealieRecipe]:
        """Dictionary of { recipe.id: MealieRecipe }"""

        return {recipe.id: recipe for recipe in self._client.get_all_recipes()}

    @cached_property
    def food_store(self) -> dict[str, Food]:
        """Dictionary of { food.name.lower(): Food }"""

        return {food.name.lower(): food for food in self._client.get_all_foods()}

    @cached_property
    def label_store(self) -> dict[str, Label]:
        """Dictionary of { label.name.lower(): Label }"""

        return {label.name.lower(): label for label in self._client.get_all_labels()}

    def get_recipe_url(self, recipe_id: str) -> Optional[str]:
        """Constructs a recipe's frontend URL using its id"""

        recipe = self.recipe_store.get(recipe_id)
        if not recipe:
            return None

        return f"{self.config.base_url}/recipe/{recipe.slug}"

    @cache
    def get_food(self, food: str) -> Optional[Food]:
        """Compares food to the Mealie food store and finds the closest match within threshold"""

        user_food = food.lower()  # food store keys are all lowercase
        if user_food in self.food_store:
            return self.food_store[user_food]

        # if we're only checking for exact matches, stop here
        if self.config.confidence_threshold >= 1:
            return None

        nearest_match: str
        threshold: int  # score from 0 - 100
        nearest_match, threshold = process.extractOne(user_food, self.food_store.keys())

        return self.food_store[nearest_match] if threshold >= self.config.confidence_threshold * 100 else None

    @cache
    def get_label(self, label: str) -> Optional[Label]:
        """Compares label to the Mealie label store and finds an exact match"""

        return self.label_store.get(label.lower())

    def get_label_from_item(self, item: MealieShoppingListItemOut) -> Optional[Label]:
        if item.label:
            return item.label

        # Mealie doesn't always add the food's label to the item, so we check the food
        elif item.food and item.food.label:
            item.label = item.food.label
            return item.label

        return None

    def add_food_to_item(self, item: SHOPPING_LIST_ITEM) -> SHOPPING_LIST_ITEM:
        if not item.note or not self.config.use_foods:
            return item

        # if the item already has a food, we leave the food alone
        if item.food_id:
            item.is_food = True

            # Mealie doesn't always add the food's label to the item, so we check the food
            if not item.label_id:
                food = self.get_food(item.note)
                if food and food.label:
                    item.label_id = food.label.id

            return item

        food = self.get_food(item.note)
        if not (food and food.id):
            return item

        if self.config.overwrite_original_item_names:
            item.food_id = food.id
            item.is_food = True

            if not item.extras:
                item.extras = MealieShoppingListItemExtras()

            if not item.extras.original_value:
                item.extras.original_value = item.note

            item.note = None

        # add the food label regardless of settings
        if food.label and not item.label_id:
            item.label_id = food.label.id

        return item

    @cache
    def get_all_lists(self) -> Iterable[MealieShoppingListOut]:
        return self._client.get_all_shopping_lists()

    def get_all_list_items(self, list_id: str, include_checked: bool = False) -> list[MealieShoppingListItemOut]:
        """
        Fetch all list items from Mealie or local cache. Sometimes contains checked items

        Optionally include all checked items queried directly from Mealie
        """

        # checked items are not always cached, so we only check the cache if we don't care about them
        if list_id in self.list_items_by_list_id and not include_checked:
            return self.list_items_by_list_id[list_id]

        list_items = list(self._client.get_all_shopping_list_items(list_id, include_checked))
        self.list_items_by_list_id[list_id] = list_items
        return list_items

    def get_item(self, list_id: str, item_id: str) -> Optional[MealieShoppingListItemOut]:
        for item in self.get_all_list_items(list_id):
            if item.id == item_id:
                return item

        return None

    def get_item_by_extra(
        self, list_id: str, extras_key: str, extras_value: str
    ) -> Optional[MealieShoppingListItemOut]:
        for item in self.get_all_list_items(list_id):
            if not item.extras:
                continue

            extras = item.extras.dict()
            if extras.get(extras_key) == extras_value:
                return item

        return None

    def _handle_list_item_changes(self, items_collection: MealieShoppingListItemsCollectionOut) -> None:
        """Updates internal list states after a bulk operation"""

        # created items
        for new_item in items_collection.created_items:
            list_items = self.get_all_list_items(new_item.shopping_list_id)
            list_items.append(new_item)

        # updated items
        updated_items_by_list_id: dict[str, list[MealieShoppingListItemOut]] = {}
        for updated_item in items_collection.updated_items:
            updated_items_by_list_id.setdefault(updated_item.shopping_list_id, []).append(updated_item)

        for list_id, updated_items in updated_items_by_list_id.items():
            list_items = self.get_all_list_items(list_id)
            item_id_by_index = {existing_item.id: i for i, existing_item in enumerate(list_items)}
            for updated_item in updated_items:
                # this should never happen since we track all list modifications
                if updated_item.id not in item_id_by_index:
                    list_items.append(updated_item)
                    continue

                index = item_id_by_index[updated_item.id]
                list_items[index] = updated_item

        # deleted items
        deleted_items_by_list_id: dict[str, list[MealieShoppingListItemOut]] = {}
        for deleted_item in items_collection.deleted_items:
            deleted_items_by_list_id.setdefault(deleted_item.shopping_list_id, []).append(deleted_item)

        for list_id, deleted_items in deleted_items_by_list_id.items():
            deleted_item_ids = [deleted_item.id for deleted_item in deleted_items]
            list_items = self.get_all_list_items(list_id)
            list_items[:] = [existing_item for existing_item in list_items if existing_item.id not in deleted_item_ids]

    def create_items(self, items: list[MealieShoppingListItemCreate]) -> None:
        if not items:
            return

        if self.config.use_foods:
            for item in items:
                item = self.add_food_to_item(item)

        items_collection = self._client.create_shopping_list_items(items)
        self._handle_list_item_changes(items_collection)

    def update_items(self, items: list[MealieShoppingListItemUpdateBulk]) -> None:
        if not items:
            return

        items_collection = self._client.update_shopping_list_items(items)
        self._handle_list_item_changes(items_collection)

    def delete_items(self, items: list[MealieShoppingListItemOut]) -> None:
        if not items:
            return

        self._client.delete_shopping_list_items([item.id for item in items])
        self._handle_list_item_changes(MealieShoppingListItemsCollectionOut(deleted_items=items))

    def bulk_handle_items(
        self,
        create_items: list[MealieShoppingListItemCreate],
        update_items: list[MealieShoppingListItemUpdateBulk],
        delete_items: list[MealieShoppingListItemOut],
    ) -> None:
        # items are handled in this order to prevent merge conflicts (e.g. creating items can result in updating items)
        self.delete_items(delete_items)
        self.update_items(update_items)
        self.create_items(create_items)
