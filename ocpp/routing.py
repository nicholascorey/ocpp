import functools
from argparse import Action
from typing import Any, Callable, TypeVar

from ocpp.v16 import ChargePoint, call, call_result, enums

routables: list[str] = []


ChargePointT = TypeVar("ChargePointT", bound=ChargePoint)
CallT = TypeVar("CallT", bound=call.CallMessageType)
ResponseT = TypeVar("ResponseT", bound=call_result.ResponseMessageType)

TypedOcppCallHandler = Callable[[ChargePointT, CallT], ResponseT]
UntypedOcppCallHandler = Callable[..., ResponseT]

TypedHandlerDecorator = Callable[
    [TypedOcppCallHandler[ChargePointT, CallT, ResponseT]],
    UntypedOcppCallHandler[ResponseT],
]
UntypedHandlerDecorator = Callable[
    [UntypedOcppCallHandler[ResponseT]],
    UntypedOcppCallHandler[ResponseT],
]


def on_typed(
    call_type: type[CallT], skip_schema_validation: bool = False
) -> TypedHandlerDecorator[ChargePointT, CallT, ResponseT]:

    def decorator(
        func: TypedOcppCallHandler[ChargePointT, CallT, ResponseT],
    ) -> UntypedOcppCallHandler[ResponseT]:
        @functools.wraps(func)
        def inner(self: ChargePointT, **kwargs: dict[str, Any]):
            request = call_type(**kwargs)
            return func(self, request)

        inner._on_action = enums.Action(call_type.__name__)
        inner._skip_schema_validation = skip_schema_validation
        if func.__name__ not in routables:
            routables.append(func.__name__)
        return inner

    return decorator


def on(
    action: Action, *, skip_schema_validation: bool = False
) -> UntypedHandlerDecorator[ResponseT]:
    """
    Function decorator to mark function as handler for specific action. The
    wrapped function may be async or sync.

    The handler function will receive keyword arguments derived from the
    payload of the specific action. It's recommended you use `**kwargs` in your
    definition to ignore any extra arguments that may be added in the future.

    The handler function should return a relevant payload to be returned to the
    Charge Point.

    It can be used like so:

    ```
    class MyChargePoint(cp):
        @on(Action.boot_notification):
        async def on_boot_notification(
            self,
            charge_point_model,
            charge_point_vendor,
            **kwargs,
        ):
            print(f'{charge_point_model} from {charge_point_vendor} booted.')

            now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + "Z"
            return call_result.BootNotificationPayload(
                current_time=now,
                interval=30,
                status="Accepted",
            )
    ```

    The decorator takes an optional argument `skip_schema_validation` which
    defaults to False. Setting this argument to `True` will disable schema
    validation of the request and the response of the specific route.

    """

    def decorator(
        func: UntypedOcppCallHandler[ResponseT],
    ) -> UntypedOcppCallHandler[ResponseT]:
        @functools.wraps(func)
        def inner(*args: tuple[Any, ...], **kwargs: dict[str, Any]):
            return func(*args, **kwargs)

        inner._on_action = action
        inner._skip_schema_validation = skip_schema_validation
        if func.__name__ not in routables:
            routables.append(func.__name__)
        return inner

    return decorator


def after(action):
    """Function decorator to mark function as hook to post-request hook.

    This hook's arguments are the data that is in the payload for the specific
    action.

    It can be used like so:

        @after(Action.boot_notification):
        def after_boot_notification():
            pass

    """

    def decorator(func):
        @functools.wraps(func)
        def inner(*args, **kwargs):
            return func(*args, **kwargs)

        inner._after_action = action
        if func.__name__ not in routables:
            routables.append(func.__name__)
        return inner

    return decorator


def create_route_map(obj):
    """
    Iterates of all attributes of the class looking for attributes which
    have been decorated by the @on() decorator It returns a dictionary where
    the action name are the keys and the decorated functions are the values.

    To illustrate this with an example, consider the following function:

        class ChargePoint:

            @on(Action.boot_notification)
            def on_boot_notification(self, *args, **kwargs):
                pass

            @after(Action.boot_notification)
            def after_boot_notification(self, *args, **kwargs):
                pass


    In this case this returns:

        {
            Action.boot_notification: {
                '_on_action': <reference to 'on_boot_notification'>,
                '_after_action': <reference to 'after_boot_notification'>,
                '_skip_schema_validation': False,
            },
        }

    """
    routes = {}
    for attr_name in routables:
        for option in ["_on_action", "_after_action"]:
            try:
                attr = getattr(obj, attr_name)
                action = getattr(attr, option)

                if action not in routes:
                    routes[action] = {}

                # Routes decorated with the `@on()` decorator can be configured
                # to skip validation of the input and output. For more info see
                # the docstring of `on()`.
                if option == "_on_action":
                    routes[action]["_skip_schema_validation"] = getattr(
                        attr, "_skip_schema_validation", False
                    )

                routes[action][option] = attr

            except AttributeError:
                continue

    return routes
