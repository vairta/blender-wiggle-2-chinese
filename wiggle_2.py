bl_info = {
    "name": "Wiggle 2",
    "author": "Steve Miller",
    "version": (2, 2, 0),
    "blender": (3, 00, 0),
    "location": "3d Viewport > Animation Panel",
    "description": "在骨骼动画上模拟类似弹簧的惯性摇摆物理效果",
    "warning": "",
    "wiki_url": "https://github.com/shteeve3d/blender-wiggle-2",
    "category": "Animation",
}

### 清单 #####

# 基本物体摆动？
# 处理继承旋转？

# bugs:
# 开始播放时出现奇怪的问题？

import bpy, math
from mathutils import Vector, Matrix, Euler, Quaternion, geometry
from bpy.app.handlers import persistent

# 在M1空间返回M2
def relative_matrix(m1,m2):
    return (m2.inverted() @ m1).inverted()

def flatten(mat):
    dim = len(mat)
    return [mat[j][i] for i in range(dim) 
                      for j in range(dim)]

def reset_scene():
    for wo in bpy.context.scene.wiggle.list:
        reset_ob(bpy.data.objects.get(wo.name))
                              
def reset_ob(ob):
    wo = bpy.context.scene.wiggle.list.get(ob.name)
    for wb in wo.list:
        reset_bone(bpy.data.objects.get(wo.name).pose.bones.get(wb.name))

def reset_bone(b):
    b.wiggle.position = b.wiggle.position_last = (b.id_data.matrix_world @ Matrix.Translation(b.tail)).translation
    b.wiggle.position_head = b.wiggle.position_last_head = (b.id_data.matrix_world @ b.matrix).translation
    b.wiggle.velocity = b.wiggle.velocity_head = b.wiggle.collision_normal = b.wiggle.collision_normal_head = Vector((0,0,0))
    b.wiggle.matrix = flatten(b.id_data.matrix_world @ b.matrix)
                      
def build_list():
    bpy.context.scene.wiggle.list.clear()
    for ob in bpy.context.scene.objects:
        if ob.type != 'ARMATURE': continue
        wigglebones = []
        for b in ob.pose.bones:
            if not (b.wiggle_head or b.wiggle_tail):
                b.wiggle_enable = False
                continue
            b.wiggle_enable = True
            wigglebones.append(b)
                
        if not wigglebones:
            ob.wiggle_enable = False
            continue
        
        ob.wiggle_enable = True
        wo = bpy.context.scene.wiggle.list.add()
        wo.name = ob.name
        for b in wigglebones:
            wb = wo.list.add()
            wb.name = b.name

        
def update_prop(self,context,prop): 
    if type(self) == bpy.types.PoseBone: 
        for b in context.selected_pose_bones:
            b[prop] = self[prop]
        if prop in ['wiggle_head', 'wiggle_tail']:
            build_list()
            for b in context.selected_pose_bones:
                reset_bone(b)
        
def get_parent(b):
    p = b.parent
    if not p: return None
    par = p if (p.wiggle_enable and (not p.wiggle_mute) and ((p.wiggle_head and not p.bone.use_connect) or p.wiggle_tail)) else get_parent(p)
    return par

def length_world(b):
    return (b.id_data.matrix_world @ b.head - b.id_data.matrix_world @ b.tail).length

def collider_poll(self, object):
    return object.type == 'MESH'

def wind_poll(self, object):
    return object.field and object.field.type =='WIND'

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
            if n.dot(v.normalized()) > 0: # vec 在下面
                nv = v.normalized()
            else: # normal 在 dir 和 vec 的对面
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
#       cp = cn = Vector((0,0,0))
    
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

def update_matrix(b,last=False):
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
    
    if last:
        const = False
        for c in b.constraints:
            if c.enabled and not (c.type == 'DAMPED_TRACK'):
                const = True 
        if const:
            b.matrix = b.bone.matrix_local @ b.matrix_basis @ loc @ rot @ scale
        else:
            b.matrix = b.matrix @ loc @ rot @ scale
    b.wiggle.matrix = flatten(m2 @ rot @ scale)
    
def pin(b):
    for c in b.constraints:
        if c.type == 'DAMPED_TRACK' and c.target and not c.mute:
            b.wiggle.position = b.wiggle.position*(1-c.influence) + c.target.location*c.influence
            break

# 可以包括重力、风力等
def move(b,dg):
    dt = bpy.context.scene.wiggle.dt
    dt2 = dt * dt
    if dt:
        if b.wiggle_tail:
            damp = max(min(1-b.wiggle_damp*dt, 1),0) 
            b.wiggle.velocity=b.wiggle.velocity*damp
            F = bpy.context.scene.gravity * b.wiggle_gravity
            if b.wiggle_wind_ob:
                dir = b.wiggle_wind_ob.matrix_world.to_quaternion().to_matrix().to_4x4() @ Vector((0,0,1))
                fac = 1 - b.wiggle_wind_ob.field.wind_factor * abs(dir.dot((b.wiggle.position - b.wiggle.matrix.translation).normalized()))
                F += dir * fac * b.wiggle_wind_ob.field.strength * b.wiggle_wind / b.wiggle_mass
            b.wiggle.position += b.wiggle.velocity + F*dt2
            pin(b)
            collide(b,dg)
        
        if b.wiggle_head and not b.bone.use_connect:
            damp = max(min(1-b.wiggle_damp_head*dt,1),0)
            b.wiggle.velocity_head = b.wiggle.velocity_head*damp
            F = bpy.context.scene.gravity * b.wiggle_gravity_head
            if b.wiggle_wind_ob_head:
                dir = b.wiggle_wind_ob_head.matrix_world.to_quaternion().to_matrix().to_4x4() @ Vector((0,0,1))
                F += dir * b.wiggle_wind_ob_head.field.strength * b.wiggle_wind_head / b.wiggle_mass_head
            b.wiggle.position_head += b.wiggle.velocity_head + F*dt2
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
        
        # 弹性
        if b.wiggle_head and not b.bone.use_connect:
            target = mat.translation
            s = spring(target, b.wiggle.position_head, b.wiggle_stiff_head)
            if p and b.wiggle_chain_head:
                if p.wiggle_tail:
                    fac = get_fac(b.wiggle_mass_head, p.wiggle_mass)
                    p.wiggle.position -= s*fac
                else:
                    fac = get_fac(b.wiggle_mass_head, p.wiggle_mass_head)
                    p.wiggle.position_head -= s*fac
                b.wiggle.position_head += s*(1-fac)
            else:
                b.wiggle.position_head += s

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
            if p and b.wiggle_chain and p.wiggle_tail: # and b.bone.use_connect:
                fac = get_fac(b.wiggle_mass, p.wiggle_mass) if i else p.wiggle_stretch
                if p == b.parent and b.bone.use_connect: # 直接父级优化
                    p.wiggle.position -= s*fac
                else:
                    headpos = mat.translation
                    
                    v1 = headpos-p.wiggle.matrix.translation
                    headpos -= s*fac
                    v2 = headpos-p.wiggle.matrix.translation
                    sc = v2.length/v1.length
                    q = v1.rotation_difference(v2)
                    v3 = q @ (p.wiggle.position - p.wiggle.matrix.translation)
                    p.wiggle.position = p.wiggle.matrix.translation + v3*sc
#                else: #implied wiggle head
#                    fac = get_fac(b.wiggle_mass, p.wiggle_mass_head) if i else p.wiggle_stretch_head
#                    p.wiggle.position_head -= s*fac
                    
                b.wiggle.position += s*(1-fac)
                update_p = True
            else:
                b.wiggle.position += s
                
        # 拉伸
        if b.wiggle_head and not b.bone.use_connect:
            if p:
                if b.parent == p and p.wiggle_tail:
                    target = p.wiggle.position + (b.wiggle.position_head - p.wiggle.position).normalized()*(b.id_data.matrix_world @ b.head - b.id_data.matrix_world @ p.tail).length
                else: # 间接
                    targetpos = p.wiggle.matrix @ relative_matrix(p.matrix, b.parent.matrix) @ Vector((0,b.parent.length,0))
                    target = targetpos + (b.wiggle.position_head - targetpos).normalized()*(b.id_data.matrix_world @ b.head - b.id_data.matrix_world @ b.parent.tail).length
            elif b.parent:
                ptail = b.id_data.matrix_world @ b.parent.tail
                target = ptail + (b.wiggle.position_head - ptail).normalized() * (b.id_data.matrix_world @ b.head - b.id_data.matrix_world @ b.parent.tail).length
            else:
                target = mat.translation
            s = stretch(target, b.wiggle.position_head, b.wiggle_stretch_head)
            if p and b.wiggle_chain_head:
                if p.wiggle_tail:
                    fac = get_fac(b.wiggle_mass_head, p.wiggle_mass) if i else p.wiggle_stretch
                    tailpos = p.wiggle.matrix @ relative_matrix(p.matrix, b.parent.matrix) @ Vector((0,b.parent.length,0))
                    ratio = (p.wiggle.matrix.translation - p.wiggle.position).length/(p.wiggle.matrix.translation - tailpos).length
                    tailpos -= s*fac
                    p.wiggle.position -= s*ratio*fac
                else: # 这有什么假设吗？ （不，头部只平移，没有骨骼伸展）
                    fac = get_fac(b.wiggle_mass_head, p.wiggle_mass_head) if i else p.wiggle_stretch_head
                    p.wiggle.position_head -= s*fac
                b.wiggle.position_head += s*(1-fac)
            else:
                b.wiggle.position_head += s
                
            target = b.wiggle.position_head + (b.wiggle.position - b.wiggle.position_head).normalized()*length_world(b)
            if b.wiggle_tail: # 尾部仅相对于头部伸展
                s = stretch(target, b.wiggle.position, b.wiggle_stretch)
                if b.wiggle_chain:
                    fac = get_fac(b.wiggle_mass, b.wiggle_mass_head) if i else b.wiggle_stretch_head
                    b.wiggle.position_head -= s*fac
                    b.wiggle.position += s*(1-fac)
                else:
                    b.wiggle.position += s
            else: b.wiggle.position = target
        else: # 相对于父级或无尾部伸展
            target = mat.translation + (b.wiggle.position - mat.translation).normalized()*length_world(b)
            s = stretch(target, b.wiggle.position, b.wiggle_stretch)
            if p and b.wiggle_chain and p.wiggle_tail: # 假设 P 是直接父级？
#                if p.wiggle_tail:
                fac = get_fac(b.wiggle_mass, p.wiggle_mass) if i else p.wiggle_stretch
                if p == b.parent and b.bone.use_connect: # 直接父级尾部优化
                    p.wiggle.position -= s*fac
                else:
                    headpos = mat.translation
                    
                    v1 = headpos-p.wiggle.matrix.translation
                    headpos -= s*fac
                    v2 = headpos-p.wiggle.matrix.translation
                    sc = v2.length/v1.length
                    q = v1.rotation_difference(v2)
                    v3 = q @ (p.wiggle.position - p.wiggle.matrix.translation)
                    p.wiggle.position = p.wiggle.matrix.translation + v3*sc

#                else: #implied p.wiggle_head
#                    fac = get_fac(b.wiggle_mass, p.wiggle_mass_head) if i else p.wiggle_stretch_head
#                    p.wiggle.position_head -= s*fac
                b.wiggle.position += s*(1-fac)
                update_p = True
            else:
                b.wiggle.position += s

        if update_p:
            collide(p,dg)# 只会改变尾部
            update_matrix(p)
        if b.wiggle_tail:
            pin(b)
            collide(b,dg)
        if b.wiggle_head:
            collide(b,dg,True)
    update_matrix(b)
 
        
@persistent
def wiggle_pre(scene):
    if not scene.wiggle_enable:
        reset_scene()
        return
    for wo in scene.wiggle.list:
        if wo.name not in scene.objects:
            build_list()
            return
        ob = scene.objects[wo.name]
        if ob.wiggle_mute or ob.wiggle_freeze:
            reset_ob(ob)
            continue
        for wb in wo.list:
            if wb.name not in ob.pose.bones:
                build_list()
                return
            b = ob.pose.bones[wb.name]
            if b.wiggle_mute or not (b.wiggle_head or b.wiggle_tail):
                reset_bone(b)
                continue
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
    if scene.wiggle.reset: return
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
    if frames_elapsed > 4: frames_elapsed = 1 # 处理大跳跃？
    if scene.wiggle.is_preroll: frames_elapsed = 1
    scene.wiggle.dt = 1/scene.render.fps * frames_elapsed
    scene.wiggle.lastframe = scene.frame_current

    for wo in scene.wiggle.list:
        ob = scene.objects[wo.name]
        if ob.wiggle_mute or ob.wiggle_freeze: continue
        bones = []
        for wb in wo.list:
            b = ob.pose.bones[wb.name]
            if b.wiggle_mute or not (b.wiggle_head or b.wiggle_tail):
#                reset_bone(b)
                continue
            bones.append(ob.pose.bones[wb.name])
        for b in bones:
            b.wiggle.collision_normal = b.wiggle.collision_normal_head = Vector((0,0,0))
            move(b,dg)
        for i in range(scene.wiggle.iterations):
            for b in bones:
                constrain(b, scene.wiggle.iterations-1-i,dg)
        for b in bones:
            update_matrix(b,True) # 最终更新处理约束？
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
    """将活动的Wiggle设置复制到选中的骨骼"""
    bl_idname = "wiggle.copy"
    bl_label = "复制到选中"
    
    @classmethod
    def poll(cls,context):
        return context.mode in ['POSE'] and context.active_pose_bone and (len(context.selected_pose_bones)>1)
    
    def execute(self,context):
        b = context.active_pose_bone
        b.wiggle_enable = b.wiggle_enable
        b.wiggle_mute = b.wiggle_mute
        b.wiggle_head = b.wiggle_head
        b.wiggle_tail = b.wiggle_tail
        b.wiggle_head_mute = b.wiggle_head_mute
        b.wiggle_tail_mute = b.wiggle_tail_mute
        
        b.wiggle_mass = b.wiggle_mass
        b.wiggle_stiff = b.wiggle_stiff
        b.wiggle_stretch = b.wiggle_stretch
        b.wiggle_damp = b.wiggle_damp
        b.wiggle_gravity = b.wiggle_gravity
        b.wiggle_wind_ob = b.wiggle_wind_ob
        b.wiggle_wind = b.wiggle_wind
        b.wiggle_collider_type = b.wiggle_collider_type
        b.wiggle_collider = b.wiggle_collider
        b.wiggle_collider_collection = b.wiggle_collider_collection
        b.wiggle_radius = b.wiggle_radius
        b.wiggle_friction = b.wiggle_friction
        b.wiggle_bounce = b.wiggle_bounce
        b.wiggle_sticky = b.wiggle_sticky
        b.wiggle_chain = b.wiggle_chain
        
        b.wiggle_mass_head = b.wiggle_mass_head
        b.wiggle_stiff_head = b.wiggle_stiff_head
        b.wiggle_stretch_head = b.wiggle_stretch_head
        b.wiggle_damp_head = b.wiggle_damp_head
        b.wiggle_gravity_head = b.wiggle_gravity_head
        b.wiggle_wind_ob_head = b.wiggle_wind_ob_head
        b.wiggle_wind_head = b.wiggle_wind_head
        b.wiggle_collider_type_head = b.wiggle_collider_type_head
        b.wiggle_collider_head = b.wiggle_collider_head
        b.wiggle_collider_collection_head = b.wiggle_collider_collection_head
        b.wiggle_radius_head = b.wiggle_radius_head
        b.wiggle_friction_head = b.wiggle_friction_head
        b.wiggle_bounce_head = b.wiggle_bounce_head
        b.wiggle_sticky_head = b.wiggle_sticky_head
        b.wiggle_chain_head = b.wiggle_chain_head
        return {'FINISHED'}

class WiggleReset(bpy.types.Operator):
    """将场景中所有Wiggle物理模拟重置为静止状态"""
    bl_idname = "wiggle.reset"
    bl_label = "重置模拟"
    
    @classmethod
    def poll(cls,context):
        return context.scene.wiggle_enable and context.mode in ['OBJECT', 'POSE']
    
    def execute(self,context):
        context.scene.wiggle.reset = True
        context.scene.frame_set(context.scene.frame_current)
        context.scene.wiggle.reset = False
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
    """在姿势模式下全选设置过Wiggle的骨骼"""
    bl_idname = "wiggle.select"
    bl_label = "全选 Wiggle"
    
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
    """将选中对象的可见Wiggle骨骼烘焙到关键帧"""
    bl_idname = "wiggle.bake"
    bl_label = "烘培 Wiggle"
    
    @classmethod
    def poll(cls,context):
        return context.object
    
    def execute(self,context):
        def push_nla():
            if context.scene.wiggle.bake_overwrite: return
            if not context.scene.wiggle.bake_nla: return
            if not context.object.animation_data: return
            if not context.object.animation_data.action: return
            action = context.object.animation_data.action
            track = context.object.animation_data.nla_tracks.new()
            track.name = action.name
            track.strips.new(action.name, int(action.frame_range[0]), action)
            
        push_nla()
        
        bpy.ops.wiggle.reset()
            
        # 预解算
        duration = context.scene.frame_end - context.scene.frame_start
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
        # 烘培
        bpy.ops.nla.bake(frame_start = context.scene.frame_start,
                        frame_end = context.scene.frame_end,
                        only_selected = True,
                        visual_keying = True,
                        use_current_action = context.scene.wiggle.bake_overwrite,
                        bake_types={'POSE'})
        context.scene.wiggle.is_preroll = False
        context.object.wiggle_freeze = True
        if not context.scene.wiggle.bake_overwrite:
            context.object.animation_data.action.name = 'WiggleAction'
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
        
    def draw(self,context):
        row = self.layout.row()
        icon = 'HIDE_ON' if not context.scene.wiggle_enable else 'SCENE_DATA'
        row.prop(context.scene, "wiggle_enable", icon=icon, text="",emboss=False)
        if not context.scene.wiggle_enable:
            row.label(text='场景未启用')
            return
        if not context.object.type == 'ARMATURE':
            row.label(text = ' 选择骨架')
            return
#        row.label(icon='TRIA_RIGHT')
        if context.object.wiggle_freeze:
            row.prop(context.object,'wiggle_freeze',icon='FREEZE',icon_only=True,emboss=False)
            row.label(text = '烘烤后冻结 wiggle')
            return
        icon = 'HIDE_ON' if context.object.wiggle_mute else 'ARMATURE_DATA'
        row.prop(context.object,'wiggle_mute',icon=icon,icon_only=True,invert_checkbox=True,emboss=False)
        if context.object.wiggle_mute:
            row.label(text='屏蔽骨架')
            return
        if not context.active_pose_bone:
            row.label(text = ' 选择姿态骨骼')
            return
#        row.label(icon='TRIA_RIGHT')
        icon = 'HIDE_ON' if context.active_pose_bone.wiggle_mute else 'BONE_DATA'
        row.prop(context.active_pose_bone,'wiggle_mute',icon=icon,icon_only=True,invert_checkbox=True,emboss=False)
        if context.active_pose_bone.wiggle_mute:
            row.label(text='屏蔽骨骼')
            return

class WIGGLE_PT_Head(WigglePanel,bpy.types.Panel):
    bl_label = ''
    bl_parent_id = 'WIGGLE_PT_Settings'
    bl_options = {'HEADER_LAYOUT_EXPAND'}
    
    @classmethod
    def poll(cls,context):
#        return context.active_pose_bone and not context.active_pose_bone.bone.use_connect
        return context.scene.wiggle_enable and context.object and not context.object.wiggle_mute and context.active_pose_bone and not context.active_pose_bone.wiggle_mute and not context.active_pose_bone.bone.use_connect
    
    def draw_header(self,context):
        row=self.layout.row(align=True)
        row.prop(context.active_pose_bone, 'wiggle_head')
    
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
        drawprops(col,b,['wiggle_mass_head','wiggle_stiff_head','wiggle_stretch_head','wiggle_damp_head'])
        col.separator()
        col.prop(b,'wiggle_gravity_head')
        row=col.row(align=True)
        row.prop(b,'wiggle_wind_ob_head')
        sub = row.row(align=True)
        sub.ui_units_x = 5
        sub.prop(b, 'wiggle_wind_head', text='')
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
        layout.prop(b,'wiggle_chain_head')
            
class WIGGLE_PT_Tail(WigglePanel,bpy.types.Panel):
    bl_label = ''
    bl_parent_id = 'WIGGLE_PT_Settings'
    bl_options = {'HEADER_LAYOUT_EXPAND'}
    
    @classmethod
    def poll(cls,context):
#        return context.active_pose_bone
        return context.scene.wiggle_enable and context.object and not context.object.wiggle_mute and context.active_pose_bone and not context.active_pose_bone.wiggle_mute
    
    def draw_header(self,context):
        row=self.layout.row(align=True)
        row.prop(context.active_pose_bone, 'wiggle_tail')
        
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
        row=col.row(align=True)
        row.prop(b,'wiggle_wind_ob')
        sub = row.row(align=True)
        sub.ui_units_x = 5
        sub.prop(b, 'wiggle_wind', text='')
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
    bl_label = '全局设置'
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
    bl_label = '烘培 Wiggle'
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
        row = layout.row()
        row.enabled = not context.scene.wiggle.bake_overwrite
        row.prop(context.scene.wiggle, 'bake_nla')
        layout.operator('wiggle.bake')
        
class WiggleBoneItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(override={'LIBRARY_OVERRIDABLE'})
    
class WiggleItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(override={'LIBRARY_OVERRIDABLE'})  
    list: bpy.props.CollectionProperty(type=WiggleBoneItem, override={'LIBRARY_OVERRIDABLE','USE_INSERTION'})    

# 存储骨骼的属性。用户可编辑的自定义属性。内部计算的属性组
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
    iterations: bpy.props.IntProperty(name='质量', description='链式物理模拟的解算迭代次数', min=1, default=2, soft_max=10, max=100)
    loop: bpy.props.BoolProperty(name='循环模拟', description='时间线循环时继续物理模拟', default=True)
    list: bpy.props.CollectionProperty(type=WiggleItem, override={'LIBRARY_OVERRIDABLE','USE_INSERTION'})
    preroll: bpy.props.IntProperty(name = '预解算帧', description='需要解算并用于烘烤的帧数', min=0, default=0)
    is_preroll: bpy.props.BoolProperty(default=False)
    bake_overwrite: bpy.props.BoolProperty(name='覆盖当前动画', description='模拟覆盖当前所有动画', default = False)
    bake_nla: bpy.props.BoolProperty(name='创建至 NLA', description='将现有骨骼动画转移到NLA上', default = False) 
    is_rendering: bpy.props.BoolProperty(default=False)
    reset: bpy.props.BoolProperty(default=False)

def register():
    
    # 模拟切换
    
    bpy.types.Scene.wiggle_enable = bpy.props.BoolProperty(
        name = '场景启用',
        description = '在这个场景中启用wiggle',
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_enable')
    )
    bpy.types.Object.wiggle_enable = bpy.props.BoolProperty(
        name = '启用骨架',
        description = '启用选中骨架',
        default = False,
        options={'HIDDEN'},
        override={'LIBRARY_OVERRIDABLE'}
#        update=lambda s, c: update_prop(s, c, 'wiggle_enable')
    )
    bpy.types.Object.wiggle_mute = bpy.props.BoolProperty(
        name = '屏蔽骨架',
        description = '屏蔽选中骨架',
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_mute')
    )
    bpy.types.Object.wiggle_freeze = bpy.props.BoolProperty(
        name = '冻结 Wiggle',
        description = '烘焙后冻结Wiggle解算',
        default = False,
        override={'LIBRARY_OVERRIDABLE'}
    )
    bpy.types.PoseBone.wiggle_enable = bpy.props.BoolProperty(
        name = '启用骨骼',
        description = "姿态模式时，在选中骨骼上启用",
        default = False,
        options={'HIDDEN'},
        override={'LIBRARY_OVERRIDABLE'}
#        update=lambda s, c: update_prop(s, c, 'wiggle_enable')
    )
    bpy.types.PoseBone.wiggle_mute = bpy.props.BoolProperty(
        name = '屏蔽骨骼',
        description = "姿态模式时，屏蔽选中骨骼",
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_mute')
    )
    bpy.types.PoseBone.wiggle_head = bpy.props.BoolProperty(
        name = '启用头部',
        description = "姿态模式时，启用选中骨骼的头部",
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        options={'HIDDEN'},
        update=lambda s, c: update_prop(s, c, 'wiggle_head')
    )
    bpy.types.PoseBone.wiggle_tail = bpy.props.BoolProperty(
        name = '启用尾部',
        description = "姿态模式时，启用选中骨骼的尾部",
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        options={'HIDDEN'},
        update=lambda s, c: update_prop(s, c, 'wiggle_tail')
    )
    
    bpy.types.PoseBone.wiggle_head_mute = bpy.props.BoolProperty(
        name = '屏蔽头部',
        description = "屏蔽选中骨骼的头部",
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_head_mute')
    )
    bpy.types.PoseBone.wiggle_tail_mute = bpy.props.BoolProperty(
        name = '屏蔽尾部',
        description = "屏蔽选中骨骼的尾部",
        default = False,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_tail_mute')
    )
    
    # 尾部道具
    
    bpy.types.PoseBone.wiggle_mass = bpy.props.FloatProperty(
        name = '质量',
        description = '骨骼的重量',
        min = 0.01,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_mass')
    )
    bpy.types.PoseBone.wiggle_stiff = bpy.props.FloatProperty(
        name = '硬度',
        description = '刚度系数，可以是很大的数值',
        min = 0,
        default = 400,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stiff')
    )
    bpy.types.PoseBone.wiggle_stretch = bpy.props.FloatProperty(
        name = '拉伸',
        description = '拉伸变形系数，范围0到1',
        min = 0,
        default = 0,
        max=1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stretch')
    )
    bpy.types.PoseBone.wiggle_damp = bpy.props.FloatProperty(
        name = '阻尼',
        description = '阻尼系数，可以大于1',
        min = 0,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_damp')
    )
    bpy.types.PoseBone.wiggle_gravity = bpy.props.FloatProperty(
        name = '重力',
        description = '场景重力的乘数',
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_gravity')
    )
    bpy.types.PoseBone.wiggle_wind_ob = bpy.props.PointerProperty(
        name='风力', 
        description='风力对象', 
        type=bpy.types.Object, 
        poll = wind_poll, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_wind_ob')
    )
    bpy.types.PoseBone.wiggle_wind = bpy.props.FloatProperty(
        name = '风力',
        description = '风力的乘数',
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_wind')
    )
    bpy.types.PoseBone.wiggle_chain = bpy.props.BoolProperty(
        name = '链式',
        description = '物理链效果，将影响父级',
        default = True,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_chain')
    )
    
    # 头部道具
    
    bpy.types.PoseBone.wiggle_mass_head = bpy.props.FloatProperty(
        name = '质量',
        description = '骨骼的重量',
        min = 0.01,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_mass_head')
    )
    bpy.types.PoseBone.wiggle_stiff_head = bpy.props.FloatProperty(
        name = '硬度',
        description = '刚度系数，可以是很大的数值',
        min = 0,
        default = 400,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stiff_head')
    )
    bpy.types.PoseBone.wiggle_stretch_head = bpy.props.FloatProperty(
        name = '拉伸',
        description = '拉伸变形系数，范围0到1',
        min = 0,
        default = 0,
        max=1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_stretch_head')
    )
    bpy.types.PoseBone.wiggle_damp_head = bpy.props.FloatProperty(
        name = '阻尼',
        description = '阻尼系数，可以大于1',
        min = 0,
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_damp_head')
    )
    bpy.types.PoseBone.wiggle_gravity_head = bpy.props.FloatProperty(
        name = '重力',
        description = '场景重力的乘数',
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_gravity_head')
    )
    bpy.types.PoseBone.wiggle_wind_ob_head = bpy.props.PointerProperty(
        name='风力', 
        description='风力对象', 
        type=bpy.types.Object, 
        poll = wind_poll, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_wind_ob_head')
    )
    bpy.types.PoseBone.wiggle_wind_head = bpy.props.FloatProperty(
        name = '风力',
        description = '风力的乘数',
        default = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_wind_head')
    )
    bpy.types.PoseBone.wiggle_chain_head = bpy.props.BoolProperty(
        name = '链式',
        description = '物理链效果，将影响父级',
        default = True,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_chain_head')
    )
    
    # 尾部碰撞
    
    bpy.types.PoseBone.wiggle_collider_type = bpy.props.EnumProperty(
        name='碰撞类型',
        items=[('Object','Object','Collide with a selected mesh'),('Collection','Collection','Collide with all meshes in selected collection')],
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_type')
    )
    bpy.types.PoseBone.wiggle_collider = bpy.props.PointerProperty(
        name='碰撞对象', 
        description='用网格对象进行碰撞', 
        type=bpy.types.Object, 
        poll = collider_poll, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider')
    )
    bpy.types.PoseBone.wiggle_collider_collection = bpy.props.PointerProperty(
        name = '碰撞集合', 
        description='用集合进行碰撞', 
        type=bpy.types.Collection, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_collection')
    )
    
    bpy.types.PoseBone.wiggle_radius = bpy.props.FloatProperty(
        name = '半径',
        description = '产生碰撞的半径',
        min = 0,
        default = 0,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_radius')
    )
    bpy.types.PoseBone.wiggle_friction = bpy.props.FloatProperty(
        name = '摩擦',
        description = '碰撞时的摩擦力',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_friction')
    )
    bpy.types.PoseBone.wiggle_bounce = bpy.props.FloatProperty(
        name = '弹性',
        description = '碰撞时的弹跳力',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_bounce')
    )
    bpy.types.PoseBone.wiggle_sticky = bpy.props.FloatProperty(
        name = '粘性',
        description = '碰撞时的粘性程度',
        min = 0,
        default = 0,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_sticky')
    )
    
    # 头部碰撞
    
    bpy.types.PoseBone.wiggle_collider_type_head = bpy.props.EnumProperty(
        name='碰撞类型',
        items=[('Object','Object','Collide with a selected mesh'),('Collection','Collection','Collide with all meshes in selected collection')],
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_type_head')
    )
    bpy.types.PoseBone.wiggle_collider_head = bpy.props.PointerProperty(
        name='碰撞对象', 
        description='用网格对象进行碰撞', 
        type=bpy.types.Object, 
        poll = collider_poll, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_head')
    )
    bpy.types.PoseBone.wiggle_collider_collection_head = bpy.props.PointerProperty(
        name = '碰撞集合', 
        description='用集合进行碰撞', 
        type=bpy.types.Collection, 
        override={'LIBRARY_OVERRIDABLE'}, 
        update=lambda s, c: update_prop(s, c, 'wiggle_collider_collection_head')
    )
    
    bpy.types.PoseBone.wiggle_radius_head = bpy.props.FloatProperty(
        name = '半径',
        description = '产生碰撞的半径',
        min = 0,
        default = 0,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_radius_head')
    )
    bpy.types.PoseBone.wiggle_friction_head = bpy.props.FloatProperty(
        name = '摩擦',
        description = '碰撞时的摩擦力',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_friction_head')
    )
    bpy.types.PoseBone.wiggle_bounce_head = bpy.props.FloatProperty(
        name = '弹性',
        description = '碰撞时的弹跳力',
        min = 0,
        default = 0.5,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_bounce_head')
    )
    bpy.types.PoseBone.wiggle_sticky_head = bpy.props.FloatProperty(
        name = '粘性',
        description = '碰撞时的粘性程度',
        min = 0,
        default = 0,
        soft_max = 1,
        override={'LIBRARY_OVERRIDABLE'},
        update=lambda s, c: update_prop(s, c, 'wiggle_sticky_head')
    )
    
    # 内部变量
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
