bl_info = {
    "name": "Wiggle 2",
    "author": "Steve Miller",
    "version": (2, 0, 0),
    "blender": (3, 00, 0),
    "location": "3d Viewport > Animation Panel",
    "description": "Simulate spring-like physics on Bone transforms",
    "warning": "",
    "wiki_url": "https://github.com/shteeve3d/blender-wiggle-2",
    "category": "Animation",
}

### TO DO #####

# Basic object wiggle?
# handle constraints?
# handle inherit rotation
# [KINDA?] Implement a constant physics step
# [DONE] Bounciness improve
# [DONE] friction improve
# [DONE] Length stiffness 1 should have no give
# [DONE] handle indirect parents
# [DONE] indirect parent chain
# [DONE] wiggle bone position
# [DONE] head/tail collision options

# bugs:
# weird glitch when starting playback?

import bpy, math
from mathutils import Vector, Matrix, Euler, Quaternion, geometry
from bpy.app.handlers import persistent

reset = False

#return m2 in m1 space
def relative_matrix(m1,m2):
    return (m2.inverted() @ m1).inverted()

def flatten(mat):
    dim = len(mat)
    return [mat[j][i] for i in range(dim) 
                      for j in range(dim)]
                      
def reset_bone(b):
    b.wiggle.position = b.wiggle.position_last = (b.id_data.matrix_world @ Matrix.Translation(b.tail)).translation
    b.wiggle.position_head = b.wiggle.position_last_head = (b.id_data.matrix_world @ b.matrix).translation
    b.wiggle.velocity = b.wiggle.velocity_head = b.wiggle.collision_normal = b.wiggle.collision_normal_head = Vector((0,0,0))
    b.wiggle.matrix = flatten(b.id_data.matrix_world @ b.matrix)
                      
def build_list():
    bpy.context.scene.wiggle.list.clear()
    for ob in bpy.context.scene.objects:
        if ob.type != 'ARMATURE': continue
        if not ob.wiggle_enable: continue
        wo = bpy.context.scene.wiggle.list.add()
        wo.name = ob.name
        for b in ob.pose.bones:
            if b.wiggle_head or b.wiggle_tail:
                wb = wo.list.add()
                wb.name = b.name
        
def update_prop(self,context,prop): 
    if type(self) == bpy.types.PoseBone: 
        for b in context.selected_pose_bones:
            b[prop] = self[prop]
    if prop in ['wiggle_enable', 'wiggle_head', 'wiggle_tail']:
        build_list()
        for b in context.selected_pose_bones:
            reset_bone(b)
        
def get_parent(b):
    p = b.parent
    if not p: return None
    par = p if ((p.wiggle_head and not p.bone.use_connect) or p.wiggle_tail) else get_parent(p)
    return par

def length_world(b):
    return (b.id_data.matrix_world @ b.head - b.id_data.matrix_world @ b.tail).length

def collider_poll(self, object):
    return object.type == 'MESH'

def collide(b,dg,head=False):
    dt = bpy.context.scene.wiggle.dt
    
    if head:
        pos = b.wiggle.position_head
        vel = b.wiggle.velocity_head
        cp = b.wiggle.collision_point_head
        co = b.wiggle.collision_ob_head
        cn = b.wiggle.collision_normal_head
        
        collider_type = b.wiggle_collider_type_head
        wiggle_collider = b.wiggle_collider_head
        wiggle_collection = b.wiggle_collider_collection_head
        
        radius = b.wiggle_radius_head
        sticky = b.wiggle_sticky_head
        bounce = b.wiggle_bounce_head
        friction = b.wiggle_friction_head
    else:
        pos = b.wiggle.position
        vel = b.wiggle.velocity
        cp = b.wiggle.collision_point
        co = b.wiggle.collision_ob
        cn = b.wiggle.collision_normal
        
        collider_type = b.wiggle_collider_type
        wiggle_collider = b.wiggle_collider
        wiggle_collection = b.wiggle_collider_collection
        
        radius = b.wiggle_radius
        sticky = b.wiggle_sticky
        bounce = b.wiggle_bounce
        friction = b.wiggle_friction
        
    colliders = []
    if collider_type == 'Object' and wiggle_collider:
        if wiggle_collider.name in bpy.context.scene.objects:
            colliders = [wiggle_collider]
    if collider_type == 'Collection' and wiggle_collection:
        if wiggle_collection in bpy.context.scene.collection.children_recursive:
            colliders = [ob for ob in wiggle_collection.objects if ob.type == 'MESH']
    col = False
    for collider in colliders:
        cmw = collider.matrix_world
        p = collider.closest_point_on_mesh(cmw.inverted() @ pos, depsgraph=dg)
        n = (cmw.to_quaternion().to_matrix().to_4x4() @ p[2]).normalized()
        i = cmw @ p[1]
        v = i-pos
        
        if (n.dot(v.normalized()) > 0.01) or (v.length < radius) or (co and (v.length < (radius+sticky))):
            if n.dot(v.normalized()) > 0: #vec is below
                nv = v.normalized()
            else: #normal is opposite dir to vec
                nv = -v.normalized()
            pos = i + nv*radius
            
            if co:
                collision_point = co.matrix_world @ cp
                pos = pos.lerp(collision_point, friction) # min(1,friction*60*dt))
            col = True
            co = collider
            cp = relative_matrix(cmw, Matrix.Translation(pos)).translation
            cn = nv
    if not col:
        co = None
#        cp = cn = Vector((0,0,0))
    
    if head:
        b.wiggle.position_head = pos
        b.wiggle.collision_point_head = cp
        b.wiggle.collision_ob_head = co  
        b.wiggle.collision_normal_head = cn
    else:
        b.wiggle.position = pos
        b.wiggle.collision_point = cp
        b.wiggle.collision_ob = co  
        b.wiggle.collision_normal = cn

def update_matrix(b):
    loc = Matrix.Translation(Vector((0,0,0)))
    p = get_parent(b)
    if p:
        mat = p.wiggle.matrix @ relative_matrix(p.matrix, b.matrix)
        if b.bone.inherit_scale == 'FULL':
            m2 = mat
        else:
            diff = relative_matrix(p.matrix, b.matrix)
            lo = Matrix.Translation((p.wiggle.matrix @ diff).translation)
            ro = p.wiggle.matrix.to_quaternion().to_matrix().to_4x4() @ diff.to_quaternion().to_matrix().to_4x4()
            sc = Matrix.LocRotScale(None,None,(b.id_data.matrix_world @ b.matrix).decompose()[2])
            m2 = lo @ ro @ sc
            
    else:
        mat = b.id_data.matrix_world @ b.matrix
        m2 = mat
            
    if b.wiggle_head and not b.bone.use_connect:
        m2 = Matrix.Translation(b.wiggle.position_head - m2.translation) @ m2
        loc = Matrix.Translation(relative_matrix(mat, Matrix.Translation(b.wiggle.position_head)).translation)
        mat = m2
    vec = relative_matrix(m2, Matrix.Translation(b.wiggle.position)).translation
    rxz = vec.to_track_quat('Y','Z')
    rot = rxz.to_matrix().to_4x4()
    
#    if b.wiggle_head:
#        bpy.context.scene.cursor.location = b.wiggle.position
    
    if b.bone.inherit_scale == 'FULL':
        l0 = b.bone.length
        l1=relative_matrix(mat, Matrix.Translation(b.wiggle.position)).translation.length
        sy = l1/l0
    else:
        par = b.parent
        if par:
            sy=(b.id_data.matrix_world @ par.matrix @ relative_matrix(par.matrix, b.matrix).translation - b.wiggle.position).length/length_world(b)
            if p:
                sy = (p.wiggle.matrix @ relative_matrix(p.matrix, b.matrix).translation - b.wiggle.position).length/length_world(b)
        else:
            sy = (b.id_data.matrix_world @ b.matrix.translation - b.wiggle.position).length/length_world(b)
    
    if b.wiggle_head and not b.bone.use_connect:
        sy = (b.wiggle.position_head - b.wiggle.position).length/length_world(b)
        if b.bone.inherit_scale == 'FULL':
            l0=relative_matrix(mat, Matrix.Translation(b.wiggle.position)).translation.length
            l1=(b.wiggle.position_head - b.wiggle.position).length
            sy = sy*(l0/l1)
            if b.parent:
                sy = sy*(b.parent.length/b.parent.bone.length)
            
    scale = Matrix.Scale(sy,4,Vector((0,1,0)))

    b.matrix = b.matrix @ loc @ rot @ scale
    b.wiggle.matrix = flatten(m2 @ rot @ scale)
    
def pin(b):
    for c in b.constraints:
        if c.type == 'DAMPED_TRACK' and c.target and not c.mute:
            b.wiggle.position = b.wiggle.position*(1-c.influence) + c.target.location*c.influence
            break

#can include gravity, wind, etc    
def move(b,dg):
    dt = bpy.context.scene.wiggle.dt
    if dt:
        if b.wiggle_tail:
            damp = max(min(1-b.wiggle_damp*dt, 1),0) 
            b.wiggle.velocity=b.wiggle.velocity*damp
            Fg = bpy.context.scene.gravity * b.wiggle_gravity * dt * dt
            b.wiggle.position += (b.wiggle.velocity + Fg)
            pin(b)
            collide(b,dg)
        
        if b.wiggle_head and not b.bone.use_connect:
            damp = max(min(1-b.wiggle_damp_head*dt,1),0)
            b.wiggle.velocity_head = b.wiggle.velocity_head*damp
            Fg = bpy.context.scene.gravity * b.wiggle_gravity_head * dt * dt
            b.wiggle.position_head += (b.wiggle.velocity_head + Fg)
            collide(b,dg,True)
        update_matrix(b)

def constrain(b,i,dg):
    dt = bpy.context.scene.wiggle.dt
    
    def get_fac(mass1,mass2):
        return 0.5 if mass1 == mass2 else mass1/(mass1+mass2)
    
    def spring(target, position, stiff):
        s = target - position
        Fs = s * stiff / bpy.context.scene.wiggle.iterations
        return Fs*dt*dt
    
    def stretch(target, position, fac):
        s = target - position
        return s*(1-fac)

    if dt:
        p=get_parent(b)
        if p:
            mat = p.wiggle.matrix @ relative_matrix(p.matrix, b.matrix)
        else:
            mat = b.id_data.matrix_world @ b.matrix
        update_p = False  
        #spring
        if b.wiggle_head and not b.bone.use_connect:
            target = mat.translation
            b.wiggle.position_head += spring(target, b.wiggle.position_head, b.wiggle_stiff_head)

            mat = Matrix.LocRotScale(b.wiggle.position_head, mat.decompose()[1], b.matrix.decompose()[2])
            target = mat @ Vector((0,b.bone.length,0))
            if b.wiggle_tail:
                s = spring(target, b.wiggle.position, b.wiggle_stiff)
                if b.wiggle_chain:
                    fac = get_fac(b.wiggle_mass, b.wiggle_mass_head)
                    b.wiggle.position_head -= s*fac
                    b.wiggle.position += s*(1-fac)
                else:
                    b.wiggle.position += s
            else:
                b.wiggle.position = target
        else:
            mat = Matrix.LocRotScale(mat.decompose()[0], mat.decompose()[1],b.matrix.decompose()[2])
            target = mat @ Vector((0, b.bone.length,0))
            s = spring(target, b.wiggle.position, b.wiggle_stiff)
            if p and b.wiggle_chain: # and b.bone.use_connect:
                fac = get_fac(b.wiggle_mass, p.wiggle_mass) if i else p.wiggle_stretch
                if b.bone.use_connect:
                    p.wiggle.position -= s*fac
                else:
                    headpos = mat.translation
                    ratio = (p.wiggle.position - p.wiggle.matrix.translation).length/(headpos - p.wiggle.matrix.translation).length
                    headpos -=s*fac
                    p.wiggle.position = p.wiggle.matrix.translation + (headpos-p.wiggle.matrix.translation)*ratio
                b.wiggle.position += s*(1-fac)
                update_p = True
            else:
                b.wiggle.position += s
                
        #stretch
        if b.wiggle_head and not b.bone.use_connect:
            target = b.wiggle.position_head + (b.wiggle.position - b.wiggle.position_head).normalized()*length_world(b)
            if b.wiggle_tail: #tail stretch only relative to head
                s = stretch(target, b.wiggle.position, b.wiggle_stretch)
                if b.wiggle_chain:
                    fac = get_fac(b.wiggle_mass, b.wiggle_mass_head)
                    b.wiggle.position_head -= s*fac
                    b.wiggle.position += s*(1-fac)
                else:
                    b.wiggle.position += s
            else: b.wiggle.position = target
        else: #tail stretch relative to parent or none
            target = mat.translation + (b.wiggle.position - mat.translation).normalized()*length_world(b)
            s = stretch(target, b.wiggle.position, b.wiggle_stretch)
            if p and b.wiggle_chain:
                fac = get_fac(b.wiggle_mass, p.wiggle_mass) if i else p.wiggle_stretch
                if b.bone.use_connect:
                    p.wiggle.position -= s*fac
                else:
                    headpos = mat.translation
                    ratio = (p.wiggle.position - p.wiggle.matrix.translation).length/(headpos - p.wiggle.matrix.translation).length
                    headpos -=s*fac
                    p.wiggle.position = p.wiggle.matrix.translation + (headpos-p.wiggle.matrix.translation)*ratio
                b.wiggle.position += s*(1-fac)
                update_p = True
            else:
                b.wiggle.position += s

        if update_p:
            collide(p,dg)#would only be tail changing
            update_matrix(p)
        if b.wiggle_tail:
            pin(b)
            collide(b,dg)
        if b.wiggle_head:
            collide(b,dg,True)
    update_matrix(b)
 
        
@persistent
def wiggle_pre(scene):
    if not scene.wiggle_enable: return
    for wo in scene.wiggle.list:
        if wo.name not in scene.objects:
            build_list()
            return
        ob = scene.objects[wo.name]
        for wb in wo.list:
            if wb.name not in ob.pose.bones:
                build_list()
                return
            b = ob.pose.bones[wb.name]
            if not b.wiggle.collision_col:
                if b.wiggle_collider_collection:
                    b.wiggle_collider_collection = bpy.data.collections.get(b.wiggle_collider_collection.name)
                    b.wiggle.collision_col = scene.collection
                elif b.wiggle_collider_collection_head:
                    bpy.data.collections.get(b.wiggle_collider_collection_head.name)
                    b.wiggle.collision_col = scene.collection
                elif b.wiggle_collider:
                    bpy.data.objects.get(b.wiggle_collider.name)
                    b.wiggle.collision_col = scene.collection
                elif b.wiggle_collider_head:
                    bpy.data.objects.get(b.wiggle_collider_head.name)
                    b.wiggle.collision_col = scene.collection
            b.location = Vector((0,0,0))
            b.rotation_quaternion = Quaternion((1,0,0,0))
            b.rotation_euler = Vector((0,0,0))
            b.scale = Vector((1,1,1))
    bpy.context.view_layer.update()

@persistent                
def wiggle_post(scene,dg):
    global reset
    if reset: return
    if not scene.wiggle_enable: return
    if scene.wiggle.is_rendering: return

    lastframe = scene.wiggle.lastframe
    if (scene.frame_current == scene.frame_start) and (scene.wiggle.loop == False) and (scene.wiggle.is_preroll == False):
        bpy.ops.wiggle.reset()
        return
    if scene.frame_current >= lastframe:
        frames_elapsed = scene.frame_current - lastframe
    else:
        e1 = (scene.frame_end - lastframe) + (scene.frame_current - scene.frame_start) + 1
        e2 = lastframe - scene.frame_current
        frames_elapsed = min(e1,e2)
    if frames_elapsed > 4: frames_elapsed = 1 #handle large jumps?
    if scene.wiggle.is_preroll: frames_elapsed = 1
    scene.wiggle.dt = 1/scene.render.fps * frames_elapsed
    scene.wiggle.lastframe = scene.frame_current
    
    for wo in scene.wiggle.list:
        ob = scene.objects[wo.name]
        bones = []
        for wb in wo.list:
            bones.append(ob.pose.bones[wb.name])
        for b in bones:
            b.wiggle.collision_normal = b.wiggle.collision_normal_head = Vector((0,0,0))
            move(b,dg)
        for i in range(scene.wiggle.iterations):
            for b in bones:
                constrain(b, scene.wiggle.iterations-1-i,dg)
        if frames_elapsed:
            for b in bones:
                vb = Vector((0,0,0))
                if b.wiggle.collision_normal.length:
                    vb = b.wiggle.velocity.reflect(b.wiggle.collision_normal).project(b.wiggle.collision_normal)*b.wiggle_bounce
                b.wiggle.velocity = (b.wiggle.position - b.wiggle.position_last)/max(frames_elapsed,1) + vb
                vb = Vector((0,0,0)) 
                if b.wiggle.collision_normal_head.length:
                    vb = b.wiggle.velocity_head.reflect(b.wiggle.collision_normal_head).project(b.wiggle.collision_normal_head)*b.wiggle_bounce_head
                b.wiggle.velocity_head = (b.wiggle.position_head - b.wiggle.position_last_head)/max(frames_elapsed,1) + vb
                b.wiggle.position_last = b.wiggle.position
                b.wiggle.position_last_head = b.wiggle.position_head
                
@persistent        
def wiggle_render_pre(scene):
    scene.wiggle.is_rendering = True
    
@persistent
def wiggle_render_post(scene):
    scene.wiggle.is_rendering = False
    
@persistent
def wiggle_render_cancel(scene):
    scene.wiggle.is_rendering = False
            
class WiggleCopy(bpy.types.Operator):
    """Copy active wiggle settings to selected bones"""
    bl_idname = "wiggle.copy"
    bl_label = "Copy Settings to Selected"
    
    @classmethod
    def poll(cls,context):
        return context.mode in ['POSE'] and context.active_pose_bone and (len(context.selected_pose_bones)>1)
    
    def execute(self,context):
        b = context.active_pose_bone
        b.wiggle_head = b.wiggle_head
        b.wiggle_tail = b.wiggle_tail
        
        b.wiggle_mass = b.wiggle_mass
        b.wiggle_stiff = b.wiggle_stiff
        b.wiggle_stretch = b.wiggle_stretch
        b.wiggle_damp = b.wiggle_damp
        b.wiggle_gravity = b.wiggle_gravity
        b.wiggle_collider_type = b.wiggle_collider_type
        b.wiggle_collider = b.wiggle_collider
        b.wiggle_collider_collection = b.wiggle_collider_collection
        b.wiggle_radius = b.wiggle_radius
        b.wiggle_friction = b.wiggle_friction
        b.wiggle_bounce = b.wiggle_bounce
        b.wiggle_sticky = b.wiggle_sticky
        
        b.wiggle_mass_head = b.wiggle_mass_head
        b.wiggle_stiff_head = b.wiggle_stiff_head
        b.wiggle_damp_head = b.wiggle_damp_head
        b.wiggle_gravity_head = b.wiggle_gravity_head
        b.wiggle_collider_type_head = b.wiggle_collider_type_head
        b.wiggle_collider_head = b.wiggle_collider_head
        b.wiggle_collider_collection_head = b.wiggle_collider_collection_head
        b.wiggle_radius_head = b.wiggle_radius_head
        b.wiggle_friction_head = b.wiggle_friction_head
        b.wiggle_bounce_head = b.wiggle_bounce_head
        b.wiggle_sticky_head = b.wiggle_sticky_head
        return {'FINISHED'}

class WiggleReset(bpy.types.Operator):
    """Reset scene wiggle physics to rest state"""
    bl_idname = "wiggle.reset"
    bl_label = "Reset Physics"
    
    @classmethod
    def poll(cls,context):
        return context.scene.wiggle_enable and context.mode in ['OBJECT', 'POSE']
    
    def execute(self,context):
        global reset
        reset = True
        context.scene.frame_set(context.scene.frame_current)
        reset = False
        rebuild = False
        for wo in context.scene.wiggle.list:
            ob = context.scene.objects.get(wo.name)
            if not ob:
                rebuild = True
                continue
            for wb in wo.list:
                b = ob.pose.bones.get(wb.name)
                if not b:
                    rebuild = True
                    continue
                reset_bone(b)
        context.scene.wiggle.lastframe = context.scene.frame_current
        if rebuild: build_list()
        return {'FINISHED'}
    
class WiggleSelect(bpy.types.Operator):
    """Select wiggle bones on selected objects in pose mode"""
    bl_idname = "wiggle.select"
    bl_label = "Select Enabled"
    
    @classmethod
    def poll(cls,context):
        return context.mode in ['POSE']
    
    def execute(self,context):
        bpy.ops.pose.select_all(action='DESELECT')
        rebuild = False
        for wo in context.scene.wiggle.list:
            ob = context.scene.objects.get(wo.name)
            if not ob:
                rebuild = True
                continue
            for wb in wo.list:
                b = ob.pose.bones.get(wb.name)
                if not b:
                    rebuild = True
                    continue
                b.bone.select = True
        if rebuild: build_list()
        return {'FINISHED'}
    
class WiggleBake(bpy.types.Operator):
    """Bake this object's visible wiggle bones to keyframes"""
    bl_idname = "wiggle.bake"
    bl_label = "Bake Wiggle"
    
    @classmethod
    def poll(cls,context):
        return context.object
    
    def execute(self,context):
        #preroll
        duration = context.scene.frame_end - context.scene.frame_start + 1
        preroll = context.scene.wiggle.preroll
        context.scene.wiggle.is_preroll = False
        bpy.ops.wiggle.select()
        bpy.ops.wiggle.reset()
        while preroll >= 0:
            if context.scene.wiggle.loop:
                frame = context.scene.frame_end - (preroll%duration)
                context.scene.frame_set(frame)
            else:
                context.scene.frame_set(context.scene.frame_start)
            context.scene.wiggle.is_preroll = True
            preroll -= 1
        bpy.ops.nla.bake(frame_start = context.scene.frame_start,
                        frame_end = context.scene.frame_end,
                        only_selected = True,
                        visual_keying = True,
                        use_current_action = context.scene.wiggle.bake_overwrite,
                        bake_types={'POSE'})
        context.scene.wiggle.is_preroll = False
        context.object.wiggle_enable = False
        return {'FINISHED'}  

class WigglePanel:
    bl_category = 'Animation'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    
    @classmethod
    def poll(cls,context):
        return context.object  

class WIGGLE_PT_Settings(WigglePanel, bpy.types.Panel):
    bl_label = 'Wiggle 2'
    
#    def draw_header(self, context):
#        self.layout.prop(context.scene, "wiggle_enable", icon="SCENE_DATA", text="")
        
    def draw(self,context):
        row = self.layout.row(align=True)
#        row.alignment = 'LEFT'
        row.prop(context.scene, "wiggle_enable", icon="SCENE_DATA", text="")
        if not context.scene.wiggle_enable:
            row.label(text = ' Scene disabled.')
            return
        if not context.object.type == 'ARMATURE':
            row.label(text = ' Select armature.')
            return
        row.label(icon='TRIA_RIGHT')
        row.prop(context.object,'wiggle_enable',icon='ARMATURE_DATA',icon_only=True)
        if not context.object.wiggle_enable:
            row.label(text = ' Armature disabled.')
        else:
            if not context.active_pose_bone:
                row.label(text = ' Select pose bone.')
            elif context.active_pose_bone and not context.active_pose_bone.wiggle_head and not context.active_pose_bone.wiggle_tail:
                row.label(text = ' Bone disabled.')

class WIGGLE_PT_Head(WigglePanel,bpy.types.Panel):
    bl_label = ''
    bl_parent_id = 'WIGGLE_PT_Settings'
    
    @classmethod
    def poll(cls,context):
        return context.scene.wiggle_enable and context.object and context.object.wiggle_enable and context.active_pose_bone and not context.active_pose_bone.bone.use_connect
    
    def draw_header(self,context):
        self.layout.prop(context.active_pose_bone, 'wiggle_head')
    
    def draw(self,context):
        b = context.active_pose_bone
        if not b.wiggle_head: return
    
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        def drawprops(layout,b,props):
            for p in props:
                layout.prop(b, p)
        
        col = layout.column(align=True)
        drawprops(col,b,['wiggle_mass_head','wiggle_stiff_head','wiggle_damp_head'])
        col.separator()
        col.prop(b,'wiggle_gravity_head')
        col.separator()
        col.prop(b, 'wiggle_collider_type_head',text='Collisions')
        collision = False
        if b.wiggle_collider_type_head == 'Object':
            row = col.row(align=True)
            row.prop_search(b, 'wiggle_collider_head', context.scene, 'objects',text=' ')
            if b.wiggle_collider_head:
                if b.wiggle_collider_head.name in context.scene.objects:
                    collision = True
                else:
                    row.label(text='',icon='UNLINKED')
        else:
            row = col.row(align=True)
            row.prop_search(b, 'wiggle_collider_collection_head', bpy.data, 'collections', text=' ')
            if b.wiggle_collider_collection_head:
                if b.wiggle_collider_collection_head in context.scene.collection.children_recursive:
                    collision = True
                else:
                    row.label(text='',icon='UNLINKED')
            
        if collision:
            col = layout.column(align=True)
            drawprops(col,b,['wiggle_radius_head','wiggle_friction_head','wiggle_bounce_head','wiggle_sticky_head'])
            
class WIGGLE_PT_Tail(WigglePanel,bpy.types.Panel):
    bl_label = ''
    bl_parent_id = 'WIGGLE_PT_Settings'
    
    @classmethod
    def poll(cls,context):
        return context.scene.wiggle_enable and context.object and context.object.wiggle_enable and context.active_pose_bone
    
    def draw_header(self,context):
        self.layout.prop(context.active_pose_bone, 'wiggle_tail')
    
    def draw(self,context):
        b = context.active_pose_bone
        if not b.wiggle_tail: return
    
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        def drawprops(layout,b,props):
            for p in props:
                layout.prop(b, p)
                
        col = layout.column(align=True)
        drawprops(col,b,['wiggle_mass','wiggle_stiff','wiggle_stretch','wiggle_damp'])
        col.separator()
        col.prop(b,'wiggle_gravity')
        col.separator()
        col.prop(b, 'wiggle_collider_type',text='Collisions')
        collision = False
        if b.wiggle_collider_type == 'Object':
            row = col.row(align=True)
            row.prop_search(b, 'wiggle_collider', context.scene, 'objects',text=' ')
            if b.wiggle_collider:
                if b.wiggle_collider.name in context.scene.objects:
                    collision = True
                else:
                    row.label(text='',icon='UNLINKED')
        else:
            row = col.row(align=True)
            row.prop_search(b, 'wiggle_collider_collection', bpy.data, 'collections', text=' ')
            if b.wiggle_collider_collection:
                if b.wiggle_collider_collection in context.scene.collection.children_recursive:
                    collision = True
                else:
                    row.label(text='',icon='UNLINKED')
        if collision:
            col = layout.column(align=True)
            drawprops(col,b,['wiggle_radius','wiggle_friction','wiggle_bounce','wiggle_sticky'])
        layout.prop(b,'wiggle_chain')

class WIGGLE_PT_Utilities(WigglePanel,bpy.types.Panel):
    bl_label = 'Global Wiggle Utilities'
    bl_parent_id = 'WIGGLE_PT_Settings'
    bl_options = {"DEFAULT_CLOSED"}
    
    @classmethod
    def poll(cls,context):
        return context.scene.wiggle_enable
    
    def draw(self,context):
        layout = self.layout
        layout.use_property_split=True
        layout.use_property_decorate=False
        col = layout.column(align=True)
        if context.object.wiggle_enable and context.mode == 'POSE':
            col.operator('wiggle.copy')
            col.operator('wiggle.select')
        col.operator('wiggle.reset')
        layout.prop(context.scene.wiggle, 'loop')
        layout.prop(context.scene.wiggle, 'iterations')
        
class WIGGLE_PT_Bake(WigglePanel,bpy.types.Panel):
    bl_label = 'Bake Wiggle'
    bl_parent_id = 'WIGGLE_PT_Utilities'
    bl_options = {"DEFAULT_CLOSED"}
    
    @classmethod
    def poll(cls,context):
        return context.scene.wiggle_enable and context.object.wiggle_enable and context.mode == 'POSE'
    
    def draw(self,context):
        layout = self.layout
        layout.use_property_split=True
        layout.use_property_decorate=False
        layout.prop(context.scene.wiggle, 'preroll')
        layout.prop(context.scene.wiggle, 'bake_overwrite')
        layout.operator('wiggle.bake')
        
class WiggleBoneItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(override={'LIBRARY_OVERRIDABLE'})
    
class WiggleItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(override={'LIBRARY_OVERRIDABLE'})  
    list: bpy.props.CollectionProperty(type=WiggleBoneItem, override={'LIBRARY_OVERRIDABLE','USE_INSERTION'})    

#store properties for a bone. custom properties for user editable. property group for internal calculations
class WiggleBone(bpy.types.PropertyGroup):
    matrix: bpy.props.FloatVectorProperty(name = 'Matrix', size=16, subtype = 'MATRIX', override={'LIBRARY_OVERRIDABLE'})
    position: bpy.props.FloatVectorProperty(subtype='TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    position_last: bpy.props.FloatVectorProperty(subtype='TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    velocity: bpy.props.FloatVectorProperty(subtype='VELOCITY', override={'LIBRARY_OVERRIDABLE'})
    
    collision_point:bpy.props.FloatVectorProperty(subtype = 'TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    collision_ob: bpy.props.PointerProperty(type=bpy.types.Object, override={'LIBRARY_OVERRIDABLE'})
    collision_normal: bpy.props.FloatVectorProperty(subtype = 'TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    collision_col: bpy.props.PointerProperty(type=bpy.types.Collection,override={'LIBRARY_OVERRIDABLE'})
    
    position_head: bpy.props.FloatVectorProperty(subtype='TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    position_last_head: bpy.props.FloatVectorProperty(subtype='TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    velocity_head: bpy.props.FloatVectorProperty(subtype='VELOCITY', override={'LIBRARY_OVERRIDABLE'})
    
    collision_point_head:bpy.props.FloatVectorProperty(subtype = 'TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    collision_ob_head: bpy.props.PointerProperty(type=bpy.types.Object, override={'LIBRARY_OVERRIDABLE'})
    collision_normal_head: bpy.props.FloatVectorProperty(subtype = 'TRANSLATION', override={'LIBRARY_OVERRIDABLE'})
    
class WiggleObject(bpy.types.PropertyGroup):
    list: bpy.props.CollectionProperty(type=WiggleItem, override={'LIBRARY_OVERRIDABLE'})
    
class WiggleScene(bpy.types.PropertyGroup):
    dt: bpy.props.FloatProperty()
    lastframe: bpy.props.IntProperty()
    iterations: bpy.props.IntProperty(name='Quality', description='Constraint solver interations for chain physics', min=1, default=2, soft_max=8, max=20)
    loop: bpy.props.BoolProperty(name='Loop Physics', description='Physics continues as timeline loops', default=True)
    list: bpy.props.CollectionProperty(type=WiggleItem, override={'LIBRARY_OVERRIDABLE','USE_INSERTION'})
    preroll: bpy.props.IntProperty(name = 'Preroll', description='Frames to run simulation before bake', min=0, default=0)
    is_preroll: bpy.props.BoolProperty(default=False)
    bake_overwrite: bpy.props.BoolProperty(name='Overwrite', description='Bake wiggle into current action, instead of creating a new one', default = False)
    is_rendering: bpy.props.BoolProperty(default=False)

def register():
    
    #WIGGLE TOGGLES
    
    bpy.types.Scene.wiggle_enable = bpy.props.BoolProperty(
        name = 'Enable Scene',
        description = 'Enable wiggle on this scene',
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_enable')
    )
    bpy.types.Object.wiggle_enable = bpy.props.BoolProperty(
        name = 'Enable Armature',
        description = 'Enable wiggle on this armature',
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_enable')
    )
    bpy.types.PoseBone.wiggle_head = bpy.props.BoolProperty(
        name = 'Bone Head',
        description = "Enable wiggle on this bone's head",
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_head')
    )
    bpy.types.PoseBone.wiggle_tail = bpy.props.BoolProperty(
        name = 'Bone Tail',
        description = "Enable wiggle on this bone's tail",
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_tail')
    )
    
    #TAIL PROPS
    
    bpy.types.PoseBone.wiggle_mass = bpy.props.FloatProperty(
        name = 'Mass',
        description = 'Mass of bone',
        min = 0.01,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_mass')
    )
    bpy.types.PoseBone.wiggle_stiff = bpy.props.FloatProperty(
        name = 'Stiff',
        description = 'Spring stiffness coefficient, can be large numbers',
        min = 0,
        default = 400,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stiff')
    )
    bpy.types.PoseBone.wiggle_stretch = bpy.props.FloatProperty(
        name = 'Stretch',
        description = 'Bone stretchiness factor, 0 to 1 range',
        min = 0,
        default = 0,
        max=1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stretch')
    )
    bpy.types.PoseBone.wiggle_damp = bpy.props.FloatProperty(
        name = 'Damp',
        description = 'Dampening coefficient, can be greater than 1',
        min = 0,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_damp')
    )
    bpy.types.PoseBone.wiggle_gravity = bpy.props.FloatProperty(
        name = 'Gravity',
        description = 'Multiplier for scene gravity',
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_gravity')
    )
    bpy.types.PoseBone.wiggle_chain = bpy.props.BoolProperty(
        name = 'Chain',
        description = 'Bone affects its parent creating a physics chain',
        default = True,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_chain')
    )
    
    #HEAD PROPS
    
    bpy.types.PoseBone.wiggle_mass_head = bpy.props.FloatProperty(
        name = 'Mass',
        description = 'Mass of bone',
        min = 0.01,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_mass')
    )
    bpy.types.PoseBone.wiggle_stiff_head = bpy.props.FloatProperty(
        name = 'Stiff',
        description = 'Spring stiffness coefficient, can be large numbers',
        min = 0,
        default = 400,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stiff')
    )
    bpy.types.PoseBone.wiggle_stretch_head = bpy.props.FloatProperty(
        name = 'Stretch',
        description = 'Bone stretchiness factor, 0 to 1 range',
        min = 0,
        default = 0,
        max=1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stretch')
    )
    bpy.types.PoseBone.wiggle_damp_head = bpy.props.FloatProperty(
        name = 'Damp',
        description = 'Dampening coefficient, can be greater than 1',
        min = 0,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_damp')
    )
    bpy.types.PoseBone.wiggle_gravity_head = bpy.props.FloatProperty(
        name = 'Gravity',
        description = 'Multiplier for scene gravity',
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_gravity')
    )
    
    #TAIL COLLISION
    
    bpy.types.PoseBone.wiggle_collider_type = bpy.props.EnumProperty(
        name='Collider Type',
        items=[('Object','Object','Collide with a selected mesh'),('Collection','Collection','Collide with all meshes in selected collection')],
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_type')
    )
    bpy.types.PoseBone.wiggle_collider = bpy.props.PointerProperty(
        name='Collider Object', 
        description='Mesh object to collide with', 
        type=bpy.types.Object, 
        poll = collider_poll, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider')
    )
    bpy.types.PoseBone.wiggle_collider_collection = bpy.props.PointerProperty(
        name = 'Collider Collection', 
        description='Collection to collide with', 
        type=bpy.types.Collection, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_collection')
    )
    
    bpy.types.PoseBone.wiggle_radius = bpy.props.FloatProperty(
        name = 'Radius',
        description = 'Collision radius',
        min = 0,
        default = 0,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_radius')
    )
    bpy.types.PoseBone.wiggle_friction = bpy.props.FloatProperty(
        name = 'Friction',
        description = 'Friction when colliding',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_friction')
    )
    bpy.types.PoseBone.wiggle_bounce = bpy.props.FloatProperty(
        name = 'Bounce',
        description = 'Bounciness when colliding',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_bounce')
    )
    bpy.types.PoseBone.wiggle_sticky = bpy.props.FloatProperty(
        name = 'Sticky',
        description = 'Margin beyond radius to keep item stuck to surface',
        min = 0,
        default = 0,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_sticky')
    )
    
    #HEAD COLLISION
    
    bpy.types.PoseBone.wiggle_collider_type_head = bpy.props.EnumProperty(
        name='Collider Type',
        items=[('Object','Object','Collide with a selected mesh'),('Collection','Collection','Collide with all meshes in selected collection')],
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_type_head')
    )
    bpy.types.PoseBone.wiggle_collider_head = bpy.props.PointerProperty(
        name='Collider Object', 
        description='Mesh object to collide with', 
        type=bpy.types.Object, 
        poll = collider_poll, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_head')
    )
    bpy.types.PoseBone.wiggle_collider_collection_head = bpy.props.PointerProperty(
        name = 'Collider Collection', 
        description='Collection to collide with', 
        type=bpy.types.Collection, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_collection_head')
    )
    
    bpy.types.PoseBone.wiggle_radius_head = bpy.props.FloatProperty(
        name = 'Radius',
        description = 'Collision radius',
        min = 0,
        default = 0,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_radius_head')
    )
    bpy.types.PoseBone.wiggle_friction_head = bpy.props.FloatProperty(
        name = 'Friction',
        description = 'Friction when colliding',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_friction_head')
    )
    bpy.types.PoseBone.wiggle_bounce_head = bpy.props.FloatProperty(
        name = 'Bounce',
        description = 'Bounciness when colliding',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_bounce_head')
    )
    bpy.types.PoseBone.wiggle_sticky_head = bpy.props.FloatProperty(
        name = 'Sticky',
        description = 'Margin beyond radius to keep item stuck to surface',
        min = 0,
        default = 0,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_sticky_head')
    )
    
    #internal variables
    bpy.utils.register_class(WiggleBoneItem)
    bpy.utils.register_class(WiggleItem)
    bpy.utils.register_class(WiggleBone)
    bpy.types.PoseBone.wiggle = bpy.props.PointerProperty(type=WiggleBone, override={'LIBRARY_OVERRIDABLE'})
    bpy.utils.register_class(WiggleObject)
    bpy.types.Object.wiggle = bpy.props.PointerProperty(type=WiggleObject, override={'LIBRARY_OVERRIDABLE'})
    bpy.utils.register_class(WiggleScene)
    bpy.types.Scene.wiggle = bpy.props.PointerProperty(type=WiggleScene, override={'LIBRARY_OVERRIDABLE'})
    
    bpy.utils.register_class(WiggleReset)
    bpy.utils.register_class(WiggleCopy)
    bpy.utils.register_class(WiggleSelect)
    bpy.utils.register_class(WiggleBake)
    bpy.utils.register_class(WIGGLE_PT_Settings)
    bpy.utils.register_class(WIGGLE_PT_Head)
    bpy.utils.register_class(WIGGLE_PT_Tail)
    bpy.utils.register_class(WIGGLE_PT_Utilities)
    bpy.utils.register_class(WIGGLE_PT_Bake)
    
#    bpy.app.handlers.frame_change_pre.clear()
#    bpy.app.handlers.frame_change_post.clear()
#    bpy.app.handlers.render_pre.clear()
#    bpy.app.handlers.render_post.clear()
#    bpy.app.handlers.render_cancel.clear()
    
    bpy.app.handlers.frame_change_pre.append(wiggle_pre)
    bpy.app.handlers.frame_change_post.append(wiggle_post)
    bpy.app.handlers.render_pre.append(wiggle_render_pre)
    bpy.app.handlers.render_post.append(wiggle_render_post)
    bpy.app.handlers.render_cancel.append(wiggle_render_cancel)

def unregister():
    bpy.utils.unregister_class(WiggleBoneItem)
    bpy.utils.unregister_class(WiggleItem)
    bpy.utils.unregister_class(WiggleBone)
    bpy.utils.unregister_class(WiggleObject)
    bpy.utils.unregister_class(WiggleScene)
    bpy.utils.unregister_class(WiggleReset)
    bpy.utils.unregister_class(WiggleCopy)
    bpy.utils.unregister_class(WiggleSelect)
    bpy.utils.unregister_class(WiggleBake)
    bpy.utils.unregister_class(WIGGLE_PT_Settings)
    bpy.utils.unregister_class(WIGGLE_PT_Head)
    bpy.utils.unregister_class(WIGGLE_PT_Tail)
    bpy.utils.unregister_class(WIGGLE_PT_Utilities)
    bpy.utils.unregister_class(WIGGLE_PT_Bake)
    
    bpy.app.handlers.frame_change_pre.remove(wiggle_pre)
    bpy.app.handlers.frame_change_post.remove(wiggle_post)
    bpy.app.handlers.render_pre.remove(wiggle_render_pre)
    bpy.app.handlers.render_post.remove(wiggle_render_post)
    bpy.app.handlers.render_cancel.remove(wiggle_render_cancel)
    
if __name__ == "__main__":
    register()
