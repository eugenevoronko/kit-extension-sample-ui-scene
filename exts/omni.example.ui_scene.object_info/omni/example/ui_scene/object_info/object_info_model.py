# Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
__all__ = ["ObjectInfoModel"]

from pxr import Tf
from pxr import Usd
from pxr import UsdGeom
from pxr import UsdShade

from omni.ui import scene as sc
import omni.usd

# The distance to raise above the top of the object's bounding box
TOP_OFFSET = 5


class ObjectInfoModel(sc.AbstractManipulatorModel):
    """
    The model tracks the position and info of the selected object.
    """

    class PositionItem(sc.AbstractManipulatorItem):
        """
        The Model Item represents the position. It doesn't contain anything
        because we take the position directly from USD when requesting.
        """

        def __init__(self):
            super().__init__()
            self.value = [0, 0, 0]

    def __init__(self):
        super().__init__()

        # Current selected prim and material
        self.prim_paths = []
        self._prim_materials = {}
        self._positions = {}

        self._stage_listener = None
        self.position = ObjectInfoModel.PositionItem()

        # Save the UsdContext name (we currently only work with a single Context)
        usd_context = self._get_context()

        # Track selection changes
        self._events = usd_context.get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_pop(
            self._on_stage_event, name="Object Info Selection Update"
        )

    def _get_context(self) -> Usd.Stage:
        # Get the UsdContext we are attached to
        return omni.usd.get_context()

    def _notice_changed(self, notice: Usd.Notice, stage: Usd.Stage) -> None:
        """Called by Tf.Notice. Used when the current selected object changes in some way."""
        for p in notice.GetChangedInfoOnlyPaths():
            if any(path in str(p.GetPrimPath()) for path in self.prim_paths):
                self._item_changed(self.position)

    def get_item(self, identifier, path):
        if identifier == "position":
            return self.position
        if identifier == "name":
            return path
        if identifier == "material":
            return self._prim_materials[path]

    def get_as_floats(self, item, path):
        if item == self.position:
            # Requesting position
            return self._get_position(path)

        if item:
            # Get the value directly from the item
            return item.value
        return []

    def _on_stage_event(self, event):
        """Called by stage_event_stream.  We only care about selection changes."""
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._on_kit_selection_changed()

    def _on_kit_selection_changed(self):
        print("self.prim_paths:", self.prim_paths)
        """Called when a selection has changed."""
        # selection change, reset it for now
        self.prim_paths = []
        usd_context = self._get_context()
        stage = usd_context.get_stage()
        if not stage:
            return

        prim_paths = usd_context.get_selection().get_selected_prim_paths()
        if not prim_paths:
            # This turns off the manipulator when everything is deselected
            self._item_changed(self.position)
            return

        for path in prim_paths:
            prim = stage.GetPrimAtPath(path)
            if not prim.IsA(UsdGeom.Imageable):
                # Revoke the Tf.Notice listener, we don't need to update anything
                if self._stage_listener:
                    self._stage_listener.Revoke()
                    self._stage_listener = None
                return

            if not self._stage_listener:
                # This handles camera movement
                self._stage_listener = Tf.Notice.Register(
                    Usd.Notice.ObjectsChanged, self._notice_changed, stage
                )

            material, relationship = UsdShade.MaterialBindingAPI(
                prim
            ).ComputeBoundMaterial()
            if material:
                self._prim_materials[path] = str(material.GetPath())
                self._selected_objects = {}
            else:
                self._prim_materials[path] = "N/A"

        self.prim_paths = prim_paths
        print("self.prim_paths:", self.prim_paths)

        # Position is changed because new selected object has a different position
        self._item_changed(self.position)

    def _get_position(self, path):
        """Returns position of currently selected object"""
        stage = self._get_context().get_stage()
        if not stage or (path not in self.prim_paths):
            return [0, 0, 0]

        # Get position directly from USD
        prim = stage.GetPrimAtPath(path)
        box_cache = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), includedPurposes=[UsdGeom.Tokens.default_]
        )
        bound = box_cache.ComputeWorldBound(prim)
        range = bound.ComputeAlignedBox()
        bboxMin = range.GetMin()
        bboxMax = range.GetMax()

        # Find the top center of the bounding box and add a small offset upward.
        position = [(bboxMin[0] + bboxMax[0]) * 0.5, bboxMax[1] +
                    TOP_OFFSET, (bboxMin[2] + bboxMax[2]) * 0.5, ]
        self._positions[path] = position

        return position
