from functools import cache, cached_property
from typing import Optional, TypeVar, cast

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
    MealieShoppingListItemUpdate,
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

        self.shopping_lists: dict[str, MealieShoppingListOut] = {}
        """map of {shopping_list_id: shopping_list}"""

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
        if user_food in self._client.food_store:
            return self._client.food_store[user_food]

        # if we're only checking for exact matches, stop here
        if self.config.confidence_threshold >= 1:
            return None

        nearest_match: str
        threshold: int  # score from 0 - 100
        nearest_match, threshold = process.extractOne(user_food, self._client.food_store.keys())

        return self._client.food_store[nearest_match] if threshold >= self.config.confidence_threshold * 100 else None

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

    def get_all_lists(self) -> list[MealieShoppingListOut]:
        if not self.shopping_lists:
            all_lists = self._client.get_all_shopping_lists()
            self.shopping_lists = {shopping_list.id: shopping_list for shopping_list in all_lists}

        return list(self.shopping_lists.values())

    def get_list(self, list_id: str) -> MealieShoppingListOut:
        if list_id in self.shopping_lists:
            return self.shopping_lists[list_id]

        shopping_list = self._client.get_shopping_list(list_id)
        self.shopping_lists[list_id] = shopping_list
        return self._client.get_shopping_list(list_id)

    def get_item(self, list_id: str, item_id: str) -> Optional[MealieShoppingListItemOut]:
        for item in self.get_list(list_id).list_items:
            if item.id == item_id:
                return item

        return None

    def get_item_by_extra(
        self, list_id: str, extras_key: str, extras_value: str
    ) -> Optional[MealieShoppingListItemOut]:
        for item in self.get_list(list_id).list_items:
            if not item.extras:
                continue

            extras = item.extras.dict()
            if extras.get(extras_key) == extras_value:
                return item

        return None

    def create_item(
        self, item: MealieShoppingListItemCreate, allow_duplicate_item_value=False
    ) -> Optional[MealieShoppingListItemOut]:
        item = item.cast(MealieShoppingListItemCreate)  # subclasses cause conflicts
        if self.config.use_foods:
            item = self.add_food_to_item(item)

        # this only works for certain user configurations
        # TODO: get this functionality implemented in Mealie, i.e. combine items upon create
        if not allow_duplicate_item_value:
            item_value = item.note.lower() if item.note else ""
            for existing_item in self.get_list(item.shopping_list_id).list_items:
                if existing_item.display.lower() != item_value:
                    continue

                if (not item.extras) or existing_item.extras == item.extras:
                    return None

                # if the items are the same, but the new item has extras, merge them and update the existing item
                if not existing_item.extras:
                    existing_item.extras = item.extras

                else:
                    existing_item.extras.merge(item.extras)

                return self.update_item(existing_item)

        new_item = self._client.create_shopping_list_item(item)
        self.get_list(new_item.shopping_list_id).list_items.append(new_item)
        return new_item

    def update_item(self, item: MealieShoppingListItemUpdate) -> MealieShoppingListItemOut:
        item = item.cast(MealieShoppingListItemUpdate)  # subclasses cause conflicts
        if self.config.use_foods:
            item = self.add_food_to_item(item)

        updated_item = self._client.update_shopping_list_item(item)
        shopping_list = self.get_list(updated_item.shopping_list_id)

        for i, item in enumerate(shopping_list.list_items):
            if item.id == updated_item.id:
                shopping_list.list_items[i] = updated_item
                break

        return updated_item

    def delete_item(self, list_item: MealieShoppingListItemOut) -> None:
        self._client.delete_shopping_list_item(list_item.id)
        shopping_list = self.get_list(list_item.shopping_list_id)
        shopping_list.list_items[:] = [item for item in shopping_list.list_items if item.id != list_item.id]

    def remove_recipe_ingredients_from_list(self, list: MealieShoppingListOut, recipe_id: str, qty: int = 1) -> None:
        for _ in range(qty):
            self._client.remove_recipe_ingredients_from_shopping_list(list.id, recipe_id)

        shopping_list = self.get_list(list.id)
        for ref in shopping_list.recipe_references:
            if ref.recipe_id == recipe_id:
                if ref.recipe_quantity:
                    ref.recipe_quantity -= qty

                break

            if not ref.recipe_quantity or ref.recipe_quantity < 0:
                shopping_list.recipe_references[:] = [
                    ref for ref in shopping_list.recipe_references if ref.recipe_id != recipe_id
                ]
