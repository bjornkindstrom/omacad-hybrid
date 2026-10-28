"""Shared entry rules for the tool prompts."""
import functools


def leaves_sketch(prompt):
    """A solid tool started from a sketch finishes the sketch first (like Fusion 360): profiles and bodies
    can only be picked outside a sketch, and the new step must come after the sketch in the history."""
    @functools.wraps(prompt)
    def wrapper(self, *args, **kwargs):
        if self.doc.active_sketch:
            self.on_finish_sketch()
        return prompt(self, *args, **kwargs)
    return wrapper
