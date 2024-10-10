# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

bl_info = {
    "name": "Vertex Animation",
    "author": "Mox Alehin",
    "version": (1, 3),
    "blender": (4, 0, 1),
    "location": "View3D > Sidebar > Unreal Tools Tab",
    "description": "A tool for storing per frame vertex data for use in a vertex shader.",
    "warning": "",
    "doc_url": "https://github.com/MoxAlehin/unreal_tools",
    "category": "Unreal Tools",
}

import bpy
import bmesh
import math

def get_per_frame_mesh_data(context, data, objects):
    """Return a list of combined mesh data per frame"""
    meshes = []
    for i in frame_range(context.scene):
        context.scene.frame_set(i)
        depsgraph = context.evaluated_depsgraph_get()
        bm = bmesh.new()
        for ob in objects:
            eval_object = ob.evaluated_get(depsgraph)
            me = data.meshes.new_from_object(eval_object)
            me.transform(ob.matrix_world)
            bm.from_mesh(me)
            data.meshes.remove(me)
        me = data.meshes.new("mesh")
        bm.normal_update()
        bm.to_mesh(me)
        bm.free()
        me.update()
        meshes.append(me)
    return meshes

# Define available target units and corresponding max deviation values
TARGET_UNITS = [
    ('MM', "Millimeters", "Export as millimeters"),
    ('CM', "Centimeters", "Export as centimeters"),
    ('DM', "Decimeters", "Export as decimeters"),
    ('M', "Meters", "Export as meters")
]

def get_max_allowed_deviation(target_unit):
    """Return max allowed deviation based on selected target units"""
    conversion_factors = {
        'M' : 1.0,    # 1 meter
        'DM': 0.1,    # 1 decimeter
        'CM': 0.01,   # 1 centimeter
        'MM': 0.001,  # 1 millimeter
    }
    return conversion_factors.get(target_unit, 0.01)  # Default to centimeters

def find_max_deviation(meshes):
    """Find the maximum vertex offset (deviation)"""
    max_deviation = 0.0
    original = meshes[0].vertices
    
    for me in reversed(meshes):
        for v in me.vertices:
            offset = (v.co - original[v.index].co).length
            if offset > max_deviation:
                max_deviation = offset
    return max_deviation

def calculate_scale(max_deviation, target_unit):
    """Calculate the scale factor with a safety margin, returning an integer scale"""
    scale_factor = 1.0
    
    """Calculate the scale factor based on the selected target units"""
    max_allowed_deviation = get_max_allowed_deviation(target_unit)
    
    if max_deviation > 0:
        scale_factor = math.ceil(max_deviation / max_allowed_deviation)
    
    return scale_factor

def update_uv_layer(me):
    """Update or create UV layer for vertex animation"""
    uv_layer = me.uv_layers.get("vertex_anim")
    if not uv_layer:
        uv_layer = me.uv_layers.new(name="vertex_anim")
    for loop in me.loops:
        uv_layer.data[loop.index].uv = (
            (loop.vertex_index + 0.5) / len(me.vertices), 128 / 255
        )
    return uv_layer

def get_vertex_data(data, meshes, scale_factor):
    """Return lists of vertex offsets and normals from a list of mesh data"""
    original = meshes[0].vertices
    offsets = []
    normals = []
    
    # Get the current coordinate system
    coord_system = bpy.context.scene.coord_system
    
    for me in reversed(meshes):
        for v in me.vertices:
            offset = (v.co - original[v.index].co) * scale_factor
            x, y, z = offset
            if coord_system == 'BLENDER':
                offsets.extend((x, -y, z, 1))  # Blender: Y Forward, Z Up
                normals.extend(((v.normal.x + 1) * 0.5, (-v.normal.y + 1) * 0.5, (v.normal.z + 1) * 0.5, 1))
            elif coord_system == 'UE':
                offsets.extend((-y, -x, z, 1))  # Unreal Engine: X Forward, Z Up
                normals.extend(((-v.normal.y + 1) * 0.5, (-v.normal.x + 1) * 0.5, (v.normal.z + 1) * 0.5, 1))
                
        if not me.users:
            data.meshes.remove(me)
    return offsets, normals

def frame_range(scene):
    """Return a range object with with scene's frame start, end, and step"""
    return range(scene.frame_start, scene.frame_end, scene.frame_step)

def bake_vertex_data(data, offsets, normals, size, name, scale_factor):
    """Stores vertex offsets and normals in separate image textures"""
    width, height = size
    wpo_texture_name = f"T_{name}_Scale{scale_factor}_O"
    normal_texture_name = f"T_{name}_N"

    offset_texture = data.images.get(wpo_texture_name)
    if offset_texture:
        offset_texture.scale(width, height)
    else:
        offset_texture = data.images.new(
            name=wpo_texture_name,
            width=width,
            height=height,
            alpha=True,
            float_buffer=True
        )
    normal_texture = data.images.get(normal_texture_name)
    if normal_texture:
        normal_texture.scale(width, height)
    else:
        normal_texture = data.images.new(
            name=normal_texture_name,
            width=width,
            height=height,
            alpha=True
        )
    offset_texture.pixels = offsets
    normal_texture.pixels = normals

class OBJECT_OT_ProcessAnimMeshes(bpy.types.Operator):
    """Store combined per frame vertex offsets and normals for all
    selected mesh objects into separate image textures"""
    bl_idname = "object.process_anim_meshes"
    bl_label = "Process Anim Meshes"

    @property
    def allowed_modifiers(self):
        return [
            'ARMATURE', 'CAST', 'CURVE', 'DISPLACE', 'HOOK',
            'LAPLACIANDEFORM', 'LATTICE', 'MESH_DEFORM',
            'SHRINKWRAP', 'SIMPLE_DEFORM', 'SMOOTH',
            'CORRECTIVE_SMOOTH', 'LAPLACIANSMOOTH',
            'SURFACE_DEFORM', 'WARP', 'WAVE',
        ]

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob and ob.type == 'MESH' and ob.mode == 'OBJECT'

    def execute(self, context):
        data = bpy.data
        objects = [ob for ob in context.selected_objects if ob.type == 'MESH']
        vertex_count = sum([len(ob.data.vertices) for ob in objects])
        frame_count = len(frame_range(context.scene))
        current_frame = context.scene.frame_current
        target_unit = context.scene.target_units
        
        for ob in objects:
            for mod in ob.modifiers:
                if mod.type not in self.allowed_modifiers:
                    self.report(
                        {'ERROR'},
                        f"Objects with {mod.type.title()} modifiers are not allowed!"
                    )
                    return {'CANCELLED'}
        if vertex_count > 8192:
            self.report(
                {'ERROR'},
                f"Vertex count of {vertex_count :,}, exceeds limit of 8,192!"
            )
            return {'CANCELLED'}
        if frame_count > 8192:
            self.report(
                {'ERROR'},
                f"Frame count of {frame_count :,}, exceeds limit of 8,192!"
            )
            return {'CANCELLED'}
        
        meshes = get_per_frame_mesh_data(context, data, objects)
        max_deviation = find_max_deviation(meshes)
        scale_factor = calculate_scale(max_deviation, target_unit)

        for ob in objects:
            update_uv_layer(ob.data)
            offsets, normals = get_vertex_data(data, meshes, scale_factor)
            texture_size = vertex_count, frame_count
            bake_vertex_data(data, offsets, normals, texture_size, ob.name, scale_factor)
        
        context.scene.frame_set(current_frame)
        return {'FINISHED'}

class VIEW3D_PT_VertexAnimation(bpy.types.Panel):
    """Creates a Panel in 3D Viewport"""
    bl_label = "Vertex Animation"
    bl_idname = "VIEW3D_PT_vertex_animation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Unreal Tools"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        scene = context.scene
        col = layout.column(align=True)
        col.prop(scene, "frame_start", text="Frame Start")
        col.prop(scene, "frame_end", text="End")
        col.prop(scene, "frame_step", text="Step")
        
        # Add a drop-down list to select a coordinate system
        col.prop(scene, "coord_system", text="Coordinate System")
        col.prop(scene, "target_units", text="Target Units")
        row = layout.row()
        row.operator("object.process_anim_meshes")

def register():
    bpy.types.Scene.coord_system = bpy.props.EnumProperty(
        name="Coordinate System",
        description="Choose the coordinate system for texture baking",
        items=[
            ('BLENDER', "Blender", "Use Blender's coordinate system (Y Forward, Z Up)"),
            ('UE', "UE", "Use Unreal Engine's coordinate system (X Forward, Z Up)"),
        ],
        default='BLENDER',
    )
    # Add property to the scene for selecting target units
    bpy.types.Scene.target_units = bpy.props.EnumProperty(
        name="Target Units",
        description="Choose the target units for export",
        items=TARGET_UNITS,
        default='CM'
    )
    bpy.utils.register_class(OBJECT_OT_ProcessAnimMeshes)
    bpy.utils.register_class(VIEW3D_PT_VertexAnimation)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_ProcessAnimMeshes)
    bpy.utils.unregister_class(VIEW3D_PT_VertexAnimation)
    del bpy.types.Scene.coord_system

if __name__ == "__main__":
    register()
