"""InstanceTrace viewport panel.

Query by logical id is the supported inspection path. Viewport picking is a
bounds prototype and reports PICK_UNSUPPORTED when the region or instance
bounds are unavailable.
"""

from __future__ import annotations

import bpy
from bpy.props import PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import session_ops
from .state import SESSION

bl_info = {
    "name": "InstanceTrace",
    "author": "Plygonality",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > InstanceTrace",
    "description": "Query provenance for supported procedural instances",
    "category": "Object",
}


class InstanceTraceSettings(PropertyGroup):
    instance_id: StringProperty(name="Instance ID", default="")  # type: ignore[valid-type]
    manifest_path: StringProperty(name="Manifest", subtype="FILE_PATH", default="")  # type: ignore[valid-type]
    output_dir: StringProperty(name="Report Directory", subtype="DIR_PATH", default="")  # type: ignore[valid-type]
    scene_revision: StringProperty(name="Scene Revision", default="")  # type: ignore[valid-type]
    source_revision: StringProperty(name="Manifest Revision", default="")  # type: ignore[valid-type]
    capture_mode: StringProperty(name="Capture", default="")  # type: ignore[valid-type]
    origin_status: StringProperty(name="Origin", default="")  # type: ignore[valid-type]
    status: StringProperty(name="Status", default="")  # type: ignore[valid-type]


class INSTANCETRACE_OT_capture(Operator):
    bl_idname = "instancetrace.capture_trace"
    bl_label = "Capture Trace"
    bl_description = "Read evaluated instances or existing id attributes. Does not save the file"
    bl_options = {"REGISTER"}

    def execute(self, context):
        result = session_ops.capture_scene(context)
        self.report({"INFO"}, f"{result['capture_mode']} rows={result['rows']}")
        return {"FINISHED"}


class INSTANCETRACE_OT_query(Operator):
    bl_idname = "instancetrace.query_instance"
    bl_label = "Query Instance ID"
    bl_description = "Trace the logical id against the loaded manifest"
    bl_options = {"REGISTER"}

    def execute(self, context):
        report = session_ops.query_instance(context)
        self.report({"INFO"}, str(report.get("origin_status")))
        return {"FINISHED"}


class INSTANCETRACE_OT_highlight(Operator):
    bl_idname = "instancetrace.highlight_source"
    bl_label = "Highlight Source"
    bl_description = "Select a source object only when its name exists, and place an overlay empty"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        result = session_ops.highlight_source(context)
        self.report({"INFO"}, result["object"])
        return {"FINISHED"}


class INSTANCETRACE_OT_graph(Operator):
    bl_idname = "instancetrace.open_event_graph"
    bl_label = "Open Event Graph"
    bl_description = "Write a self-contained HTML event graph"
    bl_options = {"REGISTER"}

    def execute(self, context):
        path = session_ops.open_event_graph(context)
        self.report({"INFO"}, path or "no query")
        return {"FINISHED"}


class INSTANCETRACE_OT_lost(Operator):
    bl_idname = "instancetrace.show_lost_lineage"
    bl_label = "Show Lost Lineage"
    bl_description = "List loss points from the current query"
    bl_options = {"REGISTER"}

    def execute(self, context):
        session_ops.show_lost_lineage(context)
        self.report({"INFO"}, context.scene.instancetrace.origin_status or "no query")
        return {"FINISHED"}


class INSTANCETRACE_OT_pick(Operator):
    bl_idname = "instancetrace.pick_instance"
    bl_label = "Pick Instance"
    bl_description = "Raycast captured bounds. Overlaps are AMBIGUOUS_PICK"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        if context.area is None or context.region is None or context.area.type != "VIEW_3D":
            result = session_ops.pick_instance(context, None, None)
            self.report({"WARNING"}, result["status"])
            return {"CANCELLED"}
        from bpy_extras import view3d_utils

        mouse = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(context.region, context.region_data, mouse)
        direction = view3d_utils.region_2d_to_vector_3d(context.region, context.region_data, mouse)
        result = session_ops.pick_instance(
            context,
            (float(origin.x), float(origin.y), float(origin.z)),
            (float(direction.x), float(direction.y), float(direction.z)),
        )
        level = "WARNING" if result["status"] != "EXACT" else "INFO"
        self.report({level}, result["status"])
        return {"FINISHED"} if result["status"] != "PICK_UNSUPPORTED" else {"CANCELLED"}

    def execute(self, context):
        result = session_ops.pick_instance(context, None, None)
        self.report({"WARNING"}, result["status"])
        return {"CANCELLED"}


class INSTANCETRACE_PT_panel(Panel):
    bl_label = "InstanceTrace"
    bl_idname = "INSTANCETRACE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "InstanceTrace"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.instancetrace
        column = layout.column(align=True)
        column.label(text=f"Scene {scene.name}")
        column.label(text=f"Frame {scene.frame_current}")
        revision = settings.source_revision or "none loaded"
        column.label(text=f"Revision {revision}")
        if settings.scene_revision and settings.source_revision and settings.scene_revision != settings.source_revision:
            column.label(text="Revision incompatible with this scene field")
        if settings.capture_mode:
            column.label(text=f"Capture {settings.capture_mode}")
        if settings.origin_status:
            column.label(text=f"Origin {settings.origin_status}")
        layout.operator("instancetrace.capture_trace", icon="VIEWZOOM")
        layout.prop(settings, "instance_id")
        layout.prop(settings, "scene_revision")
        layout.prop(settings, "manifest_path")
        layout.operator("instancetrace.query_instance", icon="VIEWZOOM")
        layout.operator("instancetrace.highlight_source", icon="OBJECT_DATA")
        layout.operator("instancetrace.open_event_graph", icon="NODETREE")
        layout.operator("instancetrace.show_lost_lineage", icon="INFO")
        layout.operator("instancetrace.pick_instance", icon="RESTRICT_SELECT_OFF")
        layout.prop(settings, "output_dir")
        if settings.status:
            box = layout.box()
            preview = settings.status.splitlines()[0][:120]
            box.label(text=preview)


CLASSES = (
    InstanceTraceSettings,
    INSTANCETRACE_OT_capture,
    INSTANCETRACE_OT_query,
    INSTANCETRACE_OT_highlight,
    INSTANCETRACE_OT_graph,
    INSTANCETRACE_OT_lost,
    INSTANCETRACE_OT_pick,
    INSTANCETRACE_PT_panel,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.instancetrace = PointerProperty(type=InstanceTraceSettings)


def unregister() -> None:
    SESSION.clear()
    if hasattr(bpy.types.Scene, "instancetrace"):
        del bpy.types.Scene.instancetrace
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
