"""
Object State Management System

Handles serialization, deserialization, and tracking of object state
for save/load functionality. All game objects can inherit from this
to get automatic state management.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class StateSerializable(ABC):
    """
    Base interface for objects that can have their state saved/loaded.
    Inherit from this to enable state persistence for your object.
    """
    
    def __init__(self):
        self.object_id: Optional[str] = None  # UUID from level spec
        self.object_type: str = "generic"      # Type identifier for deserialization
    
    @abstractmethod
    def serialize_state(self) -> Dict[str, Any]:
        """
        Return a dict of all state that should be saved.
        Must return a JSON-serializable dictionary.
        
        Example:
            return {
                "health": self.health,
                "position": [self.world_x, self.world_y],
                "active": self.is_active,
            }
        """
        pass
    
    @abstractmethod
    def deserialize_state(self, state: Dict[str, Any]) -> None:
        """
        Restore object state from a saved dictionary.
        Called when loading a save file.
        
        Args:
            state: Dictionary containing saved state from serialize_state()
        """
        pass
    
    def get_full_save_data(self) -> Dict[str, Any]:
        """
        Get complete save data for this object including ID and type.
        """
        return {
            "id": self.object_id,
            "type": self.object_type,
            "state": self.serialize_state(),
        }
    
    @staticmethod
    def from_save_data(data: Dict[str, Any], obj: "StateSerializable") -> None:
        """
        Restore an object from save data.
        
        Args:
            data: Dictionary from get_full_save_data()
            obj: Object instance to restore into
        """
        obj.object_id = data.get("id")
        obj.object_type = data.get("type", "generic")
        obj.deserialize_state(data.get("state", {}))


class ObjectStateManager:
    """
    Central manager for tracking and persisting all object states.
    One instance per level/world.
    """
    
    def __init__(self):
        self.objects: Dict[str, StateSerializable] = {}  # id -> object
        self.objects_by_type: Dict[str, list] = {}       # type -> [objects]
    
    def register_object(self, obj: StateSerializable, object_id: Optional[str] = None) -> None:
        """
        Register an object with the state manager.
        
        Args:
            obj: Object instance (should inherit StateSerializable)
            object_id: Optional UUID. If provided, will be assigned to the object.
        """
        # Ensure object has an object_type (fallback for non-StateSerializable objects)
        if not hasattr(obj, 'object_type') or not obj.object_type:
            obj.object_type = getattr(obj, 'name', obj.__class__.__name__).lower()
        
        # Ensure object has object_id
        if not hasattr(obj, 'object_id'):
            obj.object_id = None
        
        if object_id:
            obj.object_id = object_id
        
        if obj.object_id:
            self.objects[obj.object_id] = obj
            print(f"[ObjectStateManager] Registered {obj.object_type} with ID {obj.object_id}")
        else:
            print(f"[ObjectStateManager] WARNING: {obj.object_type} registered WITHOUT ID (cannot restore state)")
        
        # Track by type for quick lookups
        if obj.object_type not in self.objects_by_type:
            self.objects_by_type[obj.object_type] = []
        self.objects_by_type[obj.object_type].append(obj)
    
    def unregister_object(self, obj: StateSerializable) -> None:
        """Remove an object from tracking."""
        if obj.object_id and obj.object_id in self.objects:
            del self.objects[obj.object_id]
        
        if obj.object_type in self.objects_by_type:
            if obj in self.objects_by_type[obj.object_type]:
                self.objects_by_type[obj.object_type].remove(obj)
    
    def get_object(self, object_id: str) -> Optional[StateSerializable]:
        """Get object by ID."""
        return self.objects.get(object_id)
    
    def get_objects_by_type(self, object_type: str) -> list:
        """Get all objects of a specific type."""
        return self.objects_by_type.get(object_type, [])
    
    def save_all_states(self) -> Dict[str, Any]:
        """
        Save state of all registered objects.
        
        Returns:
            Dictionary mapping object IDs to their complete save data
        """
        save_data = {}
        for obj_id, obj in self.objects.items():
            try:
                save_data[obj_id] = obj.get_full_save_data()
            except Exception as e:
                print(f"[ObjectStateManager] Failed to save state for object {obj_id}: {e}")
        
        return save_data
    
    def load_all_states(self, save_data: Dict[str, Any]) -> None:
        """
        Load state for all registered objects from saved data.
        
        Args:
            save_data: Dictionary from save_all_states()
        """
        print(f"[ObjectStateManager.load_all_states] Have {len(self.objects)} registered objects")
        print(f"[ObjectStateManager.load_all_states] Trying to restore {len(save_data)} saved states")
        print(f"[ObjectStateManager.load_all_states] Registered object IDs: {list(self.objects.keys())}")
        print(f"[ObjectStateManager.load_all_states] Saved object IDs: {list(save_data.keys())}")
        
        for obj_id, data in save_data.items():
            if obj_id in self.objects:
                try:
                    StateSerializable.from_save_data(data, self.objects[obj_id])
                    print(f"[ObjectStateManager] âœ“ Loaded state for object {obj_id}")
                except Exception as e:
                    print(f"[ObjectStateManager] âœ— Failed to load state for object {obj_id}: {e}")
            else:
                print(f"[ObjectStateManager] âœ— Object {obj_id} not found in registry (have {list(self.objects.keys())})")
    
    def clear(self) -> None:
        """Clear all tracked objects."""
        self.objects.clear()
        self.objects_by_type.clear()


class SimpleObjectState(StateSerializable):
    """
    Simple implementation for basic objects with position and basic state.
    Inherit from this if your object has just position + a few simple attributes.
    """
    
    def __init__(self):
        super().__init__()
        self.world_x = 0
        self.world_y = 0
        self.active = True
    
    def serialize_state(self) -> Dict[str, Any]:
        """Save position and active state."""
        return {
            "x": int(self.world_x),
            "y": int(self.world_y),
            "active": bool(self.active),
        }
    
    def deserialize_state(self, state: Dict[str, Any]) -> None:
        """Restore position and active state."""
        self.world_x = state.get("x", 0)
        self.world_y = state.get("y", 0)
        self.active = state.get("active", True)

