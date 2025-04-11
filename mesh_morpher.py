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
    "name": "Mesh Morpher",
    "author": "Mox Alehin",
    "version": (1, 1),
    "blender": (4, 0, 1),
    "location": "View3D > Sidebar > Unreal Tools Tab",
    "description": "A tool for storing shape key data for use in a vertex shader.",
    "doc_url": "https://github.com/MoxAlehin/unreal_tools",
    "category": "Unreal Tools",
}

import bpy

def pack_normals(me, shape_key_index):
    """Stores normals in a given shape key's vertex colors"""
    if not me.vertex_colors:
        me.vertex_colors.new()
    col = me.vertex_colors[0]
    col.name = "normals"
    key = me.shape_keys.key_blocks[shape_key_index]
    normals = list(zip(*[iter(key.normals_vertex_get())]*3))
    for loop in me.loops:
        r, g, b = normals[loop.vertex_index]
        col.data[loop.index].color = ((r + 1) * 0.5, (-g + 1) * 0.5, (b + 1) * 0.5, 1)

def get_shape_key_offsets(shape_keys, num_shape_keys):
    """Return a list of vertex offset channels between shape keys"""
    keys = shape_keys.key_blocks
    original = keys[0].data
    offsets = [[] for _ in range(num_shape_keys * 3)]  # Create channels for X, Y, Z for each shape key

    for i in range(1, num_shape_keys + 1):
        target = keys[i].data
        for v1, v2 in zip(target, original):
            x, y, z = v1.co - v2.co

            # Apply Unreal Engine coordinate system transformation
            ue_x = -y    # Blender Y becomes UE X
            ue_y = x   # Blender -X becomes UE Y
            ue_z = z    # Z stays as is

            offsets[(i-1) * 3 + 0].append(ue_x)
            offsets[(i-1) * 3 + 1].append(ue_y)
            offsets[(i-1) * 3 + 2].append(ue_z)

    return offsets

def pack_offsets(ob, offsets, start_uv_index):
    """Stores shape key vertex offsets in mesh's UVs"""
    me = ob.data
    shape_keys = len(offsets) // 3
    num_uv_needed = (shape_keys // 2) * 3 + (shape_keys % 2) * 2
    required_uv_layers = start_uv_index + num_uv_needed
    if required_uv_layers > 8:
        raise ValueError("Not enough UV layers to store the specified number of shape keys.")
    
    axes = ['X', 'Y', 'Z']
    existing = len(me.uv_layers)
    uv_index = 0
    morph_index = 1
    axis_index = 0

    while uv_index + existing < required_uv_layers:
        name_parts = []

        # Первые две компоненты
        for _ in range(2):
            axis = axes[axis_index % 3]
            name_parts.append(f"{morph_index}{axis}")
            axis_index += 1
            if axis == 'Z':
                morph_index += 1

        # Если это последний UV и осей всего нечетное количество — оставляем только одну компоненту
        if uv_index + existing == required_uv_layers - 1 and axis_index % 3 != 0:
            name = f"Morph {name_parts[0]}"
        else:
            name = f"Morph {' '.join(name_parts)}"

        me.uv_layers.new(name=name)
        uv_index += 1

    for loop in me.loops:
        vertex_index = loop.vertex_index
        for i in range(num_uv_needed):

            # I don't know why, but it works)
            m1 = 1 if (i * 2) // 3 % 2 == 0 else -1 
            m2 = 1 if (i * 2 + 1) // 3 % 2 == 0 else -1 
            U = offsets[i * 2 + 0][vertex_index]
            V = offsets[i * 2 + 1][vertex_index] if i * 2 + 1 < len(offsets) else 0

            me.uv_layers[start_uv_index + i].data[loop.index].uv = (U * m1, 1 + V * m2)

class MeshMorpherSettings(bpy.types.PropertyGroup):
    bake_normal: bpy.props.BoolProperty(
        name="Bake Normal",
        description="Store specified shape key's vertex normals in vertex colors",
        default=True
    )
    normal_shape_key_index: bpy.props.IntProperty(
        name="Normal Shape Key Index",
        description="Index of the shape key to bake normals from",
        default=1,
        min=1
    )
    num_shape_keys: bpy.props.IntProperty(
        name="Number of Shape Keys",
        description="Number of shape keys to bake",
        default=1,
        min=1,
        max=4
    )
    start_uv_index: bpy.props.IntProperty(
        name="Start UV Index",
        description="Starting UV index for baking shape keys",
        default=1,
        min=0,
        max=7
    )

class OBJECT_OT_ProcessShapeKeys(bpy.types.Operator):
    """Store object's shape key offsets in its UV layers and Vertex Colors"""
    bl_idname = "object.process_shape_keys"
    bl_label = "Process Shape Keys"

    bake_normal: bpy.props.BoolProperty(
        name="Bake Normal",
        default=True
    )
    normal_shape_key_index: bpy.props.IntProperty(
        name="Normal Shape Key Index",
        default=1,
        min=1
    )
    num_shape_keys: bpy.props.IntProperty(
        name="Number of Shape Keys",
        default=1,
        min=1,
        max=4
    )
    start_uv_index: bpy.props.IntProperty(
        name="Start UV Index",
        default=1,
        min=0,
        max=7
    )

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob and ob.type == 'MESH' and ob.mode == 'OBJECT'

    def execute(self, context):
        units = context.scene.unit_settings
        ob = context.object
        shape_keys = ob.data.shape_keys

        if units.system != 'METRIC' or round(units.scale_length, 2) != 0.01:
            self.report(
                {'ERROR'},
                "Scene Units must be Metric with a Unit Scale of 0.01!"
            )
            return {'CANCELLED'}
        if not shape_keys:
            self.report({'ERROR'}, "Object has no shape keys!")
            return {'CANCELLED'}
        if len(shape_keys.key_blocks) < 1 + self.num_shape_keys:
            self.report({'ERROR'}, "Object needs additional shape keys!")
            return {'CANCELLED'}

        if self.bake_normal:
            try:
                pack_normals(ob.data, self.normal_shape_key_index)
            except IndexError:
                self.report({'ERROR'}, "Invalid shape key index for baking normals.")
                return {'CANCELLED'}
        
        try:
            offsets = get_shape_key_offsets(shape_keys, self.num_shape_keys)
            pack_offsets(ob, offsets, self.start_uv_index)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        
        return {'FINISHED'}

class VIEW3D_PT_MeshMorpher(bpy.types.Panel):
    """Creates a Panel in 3D Viewport"""
    bl_label = "Mesh Morpher"
    bl_idname = "VIEW3D_PT_mesh_morpher"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Unreal Tools"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        props = context.scene.mesh_morpher_settings
        col.prop(props, "bake_normal")
        if props.bake_normal:
            col.prop(props, "normal_shape_key_index")
        col.prop(props, "num_shape_keys")
        col.prop(props, "start_uv_index")
        op = col.operator("object.process_shape_keys")
        op.bake_normal = props.bake_normal
        op.normal_shape_key_index = props.normal_shape_key_index
        op.num_shape_keys = props.num_shape_keys
        op.start_uv_index = props.start_uv_index

def register():
    bpy.utils.register_class(MeshMorpherSettings)
    bpy.utils.register_class(OBJECT_OT_ProcessShapeKeys)
    bpy.utils.register_class(VIEW3D_PT_MeshMorpher)
    bpy.types.Scene.mesh_morpher_settings = bpy.props.PointerProperty(
        type=MeshMorpherSettings
    )

def unregister():
    bpy.utils.unregister_class(MeshMorpherSettings)
    bpy.utils.unregister_class(OBJECT_OT_ProcessShapeKeys)
    bpy.utils.unregister_class(VIEW3D_PT_MeshMorpher)
    del bpy.types.Scene.mesh_morpher_settings

if __name__ == "__main__":
    register()
