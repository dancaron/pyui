import asyncio
import ctypes
import functools

import sdl2

from pyui.geom import Rect, Size
from pyui.state import Binding
from pyui.utils import clamp, enumerate_last

from .base import View
from .stack import HStack
from .text import Text


class Button(HStack):
    interactive = True

    def __init__(self, label=None, action=None, asset="button", **options):
        contents = []
        if label is not None:
            if not isinstance(label, View):
                label = Text(label)
            contents = [label]
        super().__init__(*contents, **options)
        self.action = action
        self.pressed = False
        self.asset = asset

    def draw(self, renderer, rect):
        super().draw(renderer, rect)
        asset_name = self.asset + ".pressed" if self.pressed else self.asset
        self.env.draw(renderer, asset_name, self.frame)

    async def mousedown(self, pt):
        self.pressed = True
        return True

    async def mousemotion(self, pt):
        self.pressed = pt in self.frame

    async def mouseup(self, pt):
        self.pressed = False

    async def click(self, pt):
        if self.action:
            if asyncio.iscoroutinefunction(self.action):
                asyncio.create_task(self.action())
            else:
                self.action()


class Slider(View):
    interactive = True

    def __init__(self, value: Binding, minimum=0, maximum=100, **options):
        super().__init__(**options)
        self.minimum = minimum
        self.maximum = maximum
        self.current = value

    @property
    def span(self):
        return self.maximum - self.minimum + 1

    def minimum_size(self):
        return Size(self.env.scaled(40), self.env.scaled(20))

    def content_size(self, available):
        return Size(available.w, self.env.scaled(20))

    def draw(self, renderer, rect):
        offset = int((self.current.value - self.minimum) * (rect.width - self.env.scaled(20)) / (self.span - 1))
        slider_rect = Rect(origin=(rect.left, rect.top + self.env.scaled(7)), size=(rect.width, self.env.scaled(6)))
        knob_rect = Rect(origin=(rect.left + offset, rect.top), size=(self.env.scaled(20), self.env.scaled(20)))
        self.env.draw(renderer, "slider.track", slider_rect)
        self.env.draw(renderer, "slider.knob", knob_rect)

    def _set(self, value):
        clamped = clamp(int(value), self.minimum, self.maximum)
        if self.current.value != clamped:
            self.current.value = clamped

    async def mousemotion(self, pt):
        inner = self.frame - self.env.padding - self.env.border
        pos = pt.x - inner.left
        pct = clamp(pos / inner.width, 0.0, 1.0)
        self._set(self.minimum + (pct * self.span))

    async def click(self, pt):
        await self.mousemotion(pt)

    async def keydown(self, key, mods):
        amt = self.span // 10 if mods & sdl2.KMOD_SHIFT else 1
        if key == sdl2.SDLK_LEFT:
            self._set(self.current.value - amt)
        elif key == sdl2.SDLK_RIGHT:
            self._set(self.current.value + amt)


class TextField(View):
    interactive = True

    def __init__(self, text: Binding, placeholder=None, **options):
        super().__init__(**options)
        self.text = text
        self.placeholder = placeholder or ""
        self._start = None
        self._end = None

    @property
    def _font(self):
        return self.env.theme.font(self.env.font, self.env.font_size)

    @property
    def selection(self):
        if self._start is None or self._end is None:
            return None
        return set(range(min(self._start, self._end), max(self._start, self._end) + 1))

    def text_representation(self):
        return self.text.value

    def minimum_size(self):
        size = self._font.measure(self.placeholder)
        return Size(size.w, size.h * max(1, self.env.lines))

    def content_size(self, available):
        if self.env.lines > 0:
            h = self._font.line_height * self.env.lines
        else:
            size = self._font.measure(self.text.value, width=available.w)
            h = max(size.h, available.h)
        return Size(available.w, h)

    def draw(self, renderer, rect):
        super().draw(renderer, rect)
        self.env.draw(renderer, "textfield", self.frame)
        if self.text.value:
            self._font.draw(renderer, self.text_representation(), rect, self.env.color, selected=self.selection)
        elif self.placeholder:
            self._font.draw(renderer, self.placeholder, rect, sdl2.SDL_Color(150, 150, 150))

    async def focus(self):
        sdl2.SDL_StartTextInput()
        sdl2.SDL_SetTextInputRect(ctypes.byref(self.frame.sdl))

    async def blur(self):
        sdl2.SDL_StopTextInput()

    async def keydown(self, key, mods):
        if key == sdl2.SDLK_BACKSPACE:
            if self._start is not None and self._end is not None:
                s = min(self._start, self._end)
                e = max(self._start, self._end)
                self.text.value = self.text.value[:s] + self.text.value[e:]
                self._start = None
                self._end = None
            else:
                self.text.value = self.text.value[:-1]
        elif key == sdl2.SDLK_RETURN:
            self.text.value = self.text.value + "\n"

    async def textinput(self, text):
        self.text.value = self.text.value + text

    async def mousedown(self, pt):
        inner = self.frame - self.env.padding - self.env.border
        self._start = self._font.find(self.text.value, inner, pt)
        self._end = None
        return self._start is not None

    async def mousemotion(self, pt):
        inner = self.frame - self.env.padding - self.env.border
        idx = self._font.find(self.text.value, inner, pt)
        if idx is not None:
            self._end = idx


class SecureField(TextField):
    def text_representation(self):
        return "•" * len(self.text.value)


class SegmentedButton(HStack):
    def __init__(self, selection: Binding, action=None, **options):
        self.selection = selection
        self.action = action
        super().__init__(spacing=0, **options)

    def _index_asset(self, idx, is_last):
        if idx == 0:
            return "button" if is_last else "segment.left"
        else:
            return "segment.right" if is_last else "segment.center"

    def select(self, idx):
        if self.action:
            self.action(idx)
        self.selection.value = idx

    def content(self):
        for idx, item, is_last in enumerate_last(super().content()):
            asset = self._index_asset(idx, is_last)
            if idx == self.selection.value:
                asset += ".selected"
            action = functools.partial(self.select, idx)
            yield Button(item, action=action, asset=asset).disable(self.disabled)
