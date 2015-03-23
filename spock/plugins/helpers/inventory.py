"""
The Inventory plugin keeps track of the open window and its slots
and offers convenient methods for inventory manipulation.
"""

from spock.utils import pl_announce

# the button codes used in send_click
INV_BUTTON_LEFT = 0
INV_BUTTON_RIGHT = 1
INV_BUTTON_MIDDLE = 2

INV_SLOT_NR_CURSOR = -1
INV_WINID_CURSOR = -1  # the slot that follows the cursor
INV_WINID_PLAYER = 0  # player inventory window ID/type, not opened but updated by server
INV_ITEMID_EMPTY = -1

INV_SLOTS_PLAYER = 9  # crafting and armor
INV_SLOTS_INVENTORY = 9 * 3  # above hotbar
INV_SLOTS_HOTBAR = 9
INV_SLOTS_ADD = INV_SLOTS_INVENTORY + INV_SLOTS_HOTBAR  # always accessible

class Slot:
	def __init__(self, window, slot_nr, id=INV_ITEMID_EMPTY, damage=0, amount=0, enchants=None):
		self.window = window
		self.slot_nr = slot_nr
		self.item_id = id
		self.damage = damage
		self.amount = amount
		self.nbt = enchants

	def move_to_window(self, window, slot_nr):
		self.window, self.slot_nr = window, slot_nr

	def stacks_with(self, other):
		if self.item_id != other.item_id: return False
		if self.damage != other.damage: return False
		if self.damage != other.damage: return False
		# raise NotImplementedError('Stacks might differ by NBT data: %s %s' % (self, other))
		# if self.nbt != other.nbt: return False  # TODO implement this correctly
		return self.max_amount() != 1

	def max_amount(self):
		# TODO add the real values for ALL THE ITEMS! And blocks.
		# use some dummy values for now
		if self.item_id in (-1,
				256, 257, 258, 259, 261, 282,
				326, 327, 333, 335, 342, 343, 346, 347, 355, 358, 359, 373, 374, 379, 380, 386, 387, 398,
				403, 407, 408, 422, 417, 418, 419) \
			or self.item_id in range(267, 280) \
			or self.item_id in range(283, 287) \
			or self.item_id in range(290, 295) \
			or self.item_id in range(298, 318) \
			or self.item_id in range(2256, 2268) \
			: return 1
		# TODO some stack up to 16
		return 64

	def get_dict(self):
		""" Formats the slot for network packing. """
		data = {'id': self.item_id}
		if self.item_id != INV_ITEMID_EMPTY:
			data['damage'] = self.damage
			data['amount'] = self.amount
			if self.nbt is not None:
				data['enchants'] = self.nbt
		return data

	def __bool__(self):
		return self.item_id > 0

	def __repr__(self):
		if self.item_id != INV_ITEMID_EMPTY:
			args = str(self.get_dict()).strip('{}').replace("'", '').replace(': ', '=')
		else: args = 'empty'
		return 'Slot(window=%s, slot_nr=%i, %s)' % (self.window, self.slot_nr, args)

class SlotCursor(Slot):
	def __init__(self, id=INV_ITEMID_EMPTY, damage=0, amount=0, enchants=None):
		class CursorWindow:
			window_id = INV_WINID_CURSOR
			def __repr__(self):
				return 'CursorWindow()'
		super().__init__(CursorWindow(), INV_SLOT_NR_CURSOR, id, damage, amount, enchants)

# look up a class by window type ID when opening windows
inv_types = {}
def map_window_type(inv_type_id):
	def inner(cl):
		inv_types[inv_type_id] = cl
		cl.inv_type = inv_type_id
		return cl
	return inner

class InventoryBase:
	""" Base class for all inventory types. """

	# the arguments must have the same names as the keys in the packet dict
	def __init__(self, inv_type, window_id, title, slot_count, add_slots):
		self.inv_type = inv_type
		self.window_id = window_id
		self.title = title

		# slots vary by inventory type, but always contain main inventory and hotbar
		# create own slots, ...
		self.slots = [Slot(self, slot_nr) for slot_nr in range(slot_count)]
		# ... append player inventory slots, which have to be moved
		for slot_nr_add, inv_slot in enumerate(add_slots[-INV_SLOTS_ADD:]):
			inv_slot.move_to_window(self, slot_nr_add + slot_count)
			self.slots.append(inv_slot)

		# additional info dependent on inventory type, dynamically updated by server
		self.properties = {}

	def __repr__(self):
		return 'Inventory(id=%i, title=%s)' % (self.window_id, self.title)

	def inventory_slots(self):
		return self.slots[-INV_SLOTS_ADD:-INV_SLOTS_HOTBAR]

	def hotbar_slots(self):
		return self.slots[-INV_SLOTS_HOTBAR:]

	def window_slots(self):
		""" All slots except inventory and hotbar.
		 Useful for searching. """
		return self.slots[:-INV_SLOTS_ADD]

# no @map_window_type(), because not opened by server
class InventoryPlayer(InventoryBase):
	""" The player's inventory is always open when no other window is open. """

	name = 'Inventory'

	def __init__(self, add_slots=None):
		if add_slots is None:
			add_slots = [Slot(self, slot_nr) for slot_nr in range(INV_SLOTS_ADD)]
		super().__init__('player', INV_WINID_PLAYER, self.name, INV_SLOTS_PLAYER, add_slots)  # TODO title should be in chat format

	def craft_result_slot(self):
		return self.slots[0]

	def craft_grid_slots(self):
		return self.slots[1:5]

	def armor_slots(self):
		return self.slots[5:9]

@map_window_type('minecraft:chest')
class InventoryChest(InventoryBase):
	""" Small, large, and glitched-out superlarge chests. """

	name = 'Chest'

@map_window_type('minecraft:crafting_table')
class InventoryWorkbench(InventoryBase):
	name = 'Workbench'

	def craft_result_slot(self):
		return self.slots[0]

	def craft_grid_slots(self):
		return self.slots[1:10]

	# TODO crafting recipes? might be done in other plugin, as this is very complex

@map_window_type('minecraft:furnace')
class InventoryFurnace(InventoryBase):
	name = 'Furnace'

	def smelted_slot(self):
		return self.slots[0]

	def fuel_slot(self):
		return self.slots[1]

	def result_slot(self):
		return self.slots[2]

	def progress_prop(self):
		return self.properties[0]

	def fuel_time_prop(self):
		return self.properties[1]

@map_window_type('minecraft:dispenser')
class InventoryDispenser(InventoryBase):
	name = 'Dispenser'

@map_window_type('minecraft:enchanting_table')
class InventoryEnchant(InventoryBase):
	name = 'Encantment Table'

	def enchanted_slot(self):
		return self.slots[0]

	def lapis_slot(self):
		return self.slots[1]

	# TODO enchanting

@map_window_type('minecraft:brewing_stand')
class InventoryBrewing(InventoryBase):
	name = 'Brewing Stand'

	def ingredient_slot(self):
		return self.slots[0]

	def result_slots(self):
		return self.slots[1:4]

	def brew_time_prop(self):
		return self.properties[0]

@map_window_type('minecraft:villager')
class InventoryVillager(InventoryBase):
	name = 'NPC Trade'

	# TODO NPC slot getters
	# TODO trading

@map_window_type('minecraft:beacon')
class InventoryBeacon(InventoryBase):
	name = 'Beacon'

	def input_slot(self):
		return self.slots[0]

	def level_prop(self):
		return self.properties[0]

	def effect_one_prop(self):
		return self.properties[1]

	def effect_two_prop(self):
		return self.properties[2]

	# TODO choosing/applying the effect

@map_window_type('minecraft:anvil')
class InventoryAnvil(InventoryBase):
	name = 'Anvil'

	# TODO anvil slot getters

	def max_cost_prop(self):
		return self.properties[0]

@map_window_type('minecraft:hopper')
class InventoryHopper(InventoryBase):
	name = 'Hopper'

@map_window_type('minecraft:dropper')
class InventoryDropper(InventoryBase):
	name = 'Dropper'

@map_window_type('EntityHorse')
class InventoryHorse(InventoryBase):
	name = 'Horse'

	def __init__(self, eid=0, **args):
		super().__init__(**args)
		self.horse_entity_id = eid

	# TODO horse slot getters

class BaseClick:
	def get_packet(self, inv_plugin):
		raise NotImplementedError()

	def apply(self, inv_plugin):
		raise NotImplementedError()

	def success(self, inv_plugin, emit_set_slot):
		self.dirty = set()
		self.apply(inv_plugin)
		for changed_slot in self.dirty:
			emit_set_slot(changed_slot)
		for succ in getattr(self, 'successors', []):
			inv_plugin.send_click(succ)
		self.successors = []

	def add_successor(self, succ):
		if not hasattr(self, 'successors'):
			self.successors = []
		self.successors.append(succ)

	# helper functions, used by children

	def copy_slot_type(self, slot_from, slot_to):
		slot_to.item_id, slot_to.damage, slot_to.nbt = slot_from.item_id, slot_from.damage, slot_from.nbt
		self.mark_dirty(slot_to)

	def swap_slots(self, slot_a, slot_b):
		slot_a.item_id, slot_b.item_id = slot_b.item_id, slot_a.item_id
		slot_a.damage,  slot_b.damage  = slot_b.damage,  slot_a.damage
		slot_a.amount,  slot_b.amount  = slot_b.amount,  slot_a.amount
		slot_a.nbt,     slot_b.nbt     = slot_b.nbt,     slot_a.nbt
		self.mark_dirty(slot_a)
		self.mark_dirty(slot_b)

	def transfer(self, from_slot, to_slot, max_amount):
		amount = min(max_amount, from_slot.amount, to_slot.max_amount() - to_slot.amount)
		if amount <= 0: return
		self.copy_slot_type(from_slot, to_slot)
		to_slot.amount += amount
		from_slot.amount -= amount
		self.cleanup_if_empty(from_slot)

	def cleanup_if_empty(self, slot):
		if slot.amount <= 0:
			empty_slot_at_same_position = Slot(slot.window, slot.slot_nr)
			self.copy_slot_type(empty_slot_at_same_position, slot)
		self.mark_dirty(slot)

	def mark_dirty(self, slot):
		self.dirty.add(slot)

class SingleClick(BaseClick):
	def __init__(self, slot_nr, button=INV_BUTTON_LEFT):
		self.slot_nr = slot_nr
		self.button= button
		if button not in (INV_BUTTON_LEFT, INV_BUTTON_RIGHT):
			raise NotImplementedError('Clicking with button %s not implemented' % button)

	def get_packet(self, inv_plugin):
		return {
			'slot': self.slot_nr,
			'button': self.button,
			'mode': 0,
			'clicked_item': inv_plugin.window.slots[self.slot_nr].get_dict(),
		}

	def apply(self, inv_plugin):
		clicked = inv_plugin.window.slots[self.slot_nr]
		cursor = inv_plugin.cursor_slot
		if self.button == INV_BUTTON_LEFT:
			if clicked.stacks_with(cursor):
				self.transfer(cursor, clicked, cursor.amount)
			else:
				self.swap_slots(cursor, clicked)
		elif self.button == INV_BUTTON_RIGHT:
			if cursor.item_id == INV_ITEMID_EMPTY:
				# transfer half, round up
				self.transfer(clicked, cursor, (clicked.amount+1) // 2)
			elif clicked.item_id == INV_ITEMID_EMPTY or clicked.stacks_with(cursor):
				self.transfer(cursor, clicked, 1)
			else:  # slot items do not stack
				self.swap_slots(cursor, clicked)
		else:
			raise NotImplementedError('Clicking with button %s not implemented' % self.button)

class DropClick(BaseClick):
	def __init__(self, slot_nr, drop_stack=False):
		self.slot_nr = slot_nr
		self.drop_stack = drop_stack

	def get_packet(self, inv_plugin):
		if inv_plugin.cursor_slot.item_id != INV_ITEMID_EMPTY:
			return None  # can't drop while holding an item
		return {
			'slot': self.slot_nr,
			'button': 1 if self.drop_stack else 0,
			'mode': 4,
			'clicked_item': inv_plugin.cursor_slot.get_dict(),
		}

	def apply(self, inv_plugin):
		if inv_plugin.cursor_slot.item_id == INV_ITEMID_EMPTY:
			clicked_slot = inv_plugin.window.slots[self.slot_nr]
			if self.drop_stack:
				clicked_slot.amount = 0
			else:
				clicked_slot.amount -= 1
			self.cleanup_if_empty(clicked_slot)
		# else: can't drop while holding an item

class InventoryCore:
	""" Handles operations with the player inventory. """

	def __init__(self, net_plugin, send_click):
		self._net = net_plugin
		self.send_click = send_click
		self.selected_slot = 0
		self.cursor_slot = SlotCursor()  # the slot that moves with the mouse when clicking a slot
		self.window = InventoryPlayer()

	def total_stored(self, item_id, meta=-1, slots=None):
		"""
		Calculates the total number of items of that type
		in the current window or given slot range.
		"""
		wanted = lambda s: item_id == s.item_id and meta in (-1, s.damage)
		amount = 0
		for slot in slots or self.window.slots:
			if wanted(slot):
				amount += slot.amount
		return amount

	def find_item(self, item_id, meta=-1, start=0):
		"""
		Returns the first slot containing the item or None if not found.
		Searches held item, hotbar, player inventory, open window in this order.
		"""

		wanted = lambda s: s.slot_nr >= start \
							and item_id == s.item_id \
							and meta in (-1, s.damage)

		slot = self.window.hotbar_slots()[self.selected_slot]
		if wanted(slot):
			return self.selected_slot + self.window.hotbar_slots()[0].slot_nr
		# not selected, search for it
		# hotbar is at the end of the inventory, search there first
		for nr, slot in enumerate(self.window.hotbar_slots()):
			if wanted(slot):
				return nr + self.window.hotbar_slots()[0].slot_nr
		# not in hotbar, search inventory
		for nr, slot in enumerate(self.window.inventory_slots()):
			if wanted(slot):
				return nr + self.window.inventory_slots()[0].slot_nr
		# not in inventory, search open window's slots
		for nr, slot in enumerate(self.window.window_slots()):
			if wanted(slot):
				return nr
		return None

	def hold_item(self, item_id, meta=-1):
		"""
		Tries to place a stack of the specified item ID
		in the hotbar and select it.
		Returns True if done, False if failed, otherwise a
		unique event name, which is later emitted exactly once.
		"""

		slot_nr = self.find_item(item_id, meta)
		if slot_nr is None: return False
		hotbar_slot_nr = slot_nr - self.hotbar_start()
		if hotbar_slot_nr >= 0:
			return self.select_slot(hotbar_slot_nr)
		else:
			return self.swap_with_hotbar(slot_nr)

	def select_slot(self, slot_nr):
		if not 0 <= slot_nr < INV_SLOTS_HOTBAR:
			return False
		if slot_nr != self.selected_slot:
			self.selected_slot = slot_nr
			self._net.push_packet('PLAY>Held Item Change', {'slot': slot_nr})
		return True

	def swap_with_hotbar(self, slot, hotbar_slot=None):
		if hotbar_slot is None: hotbar_slot = self.selected_slot
		# TODO not implemented yet (see simulate_click)
		# will be something like:
		# return self.send_click(SwapClick(slot, hotbar_slot))
		return self.swap_slots(slot, hotbar_slot + self.hotbar_start())

	def click_slot(self, slot, right=False):
		button = INV_BUTTON_RIGHT if right else INV_BUTTON_LEFT
		return self.send_click(SingleClick(slot, button))

	def swap_slots(self, slot_a, slot_b):
		# pick up A
		one = SingleClick(slot_a)
		# pick up B, place A at B's position
		two = SingleClick(slot_b)
		# place B at A's original position
		three = SingleClick(slot_a)
		one.add_successor(two)
		two.add_successor(three)
		return self.send_click(one)

	def drop_item(self, slot=None, drop_stack=False):
		if slot is None:  # drop held item
			slot = self.selected_slot + self.hotbar_start()
		return self.send_click(DropClick(slot, drop_stack))

	# TODO is/should this be implemented somewhere else?
	def interact_with_block(self, coords):
		"""
		Clicks on a block to open its window.
		:param coords: Vec3 with the block coordinates
		"""
		self._net.push_packet('PLAY>Player Block Placement', {
			'location': coords.get_dict(),
			'direction': 1,
			'held_item': self.get_held_item().get_dict(),
			'cur_pos_x': 8,
			'cur_pos_y': 8,
			'cur_pos_z': 8,
		})

	# TODO is/should this be implemented somewhere else?
	def interact_with_entity(self, entity_id):
		""" Clicks on an entity to open its window. """
		self._net.push_packet('PLAY>Use Entity', {'target': entity_id, 'action': 0})

	def close_window(self):
		self._net.push_packet('PLAY>Close Window', {'window_id': self.window.window_id})

	def get_held_item(self):
		return self.window.slots[self.selected_slot + self.hotbar_start()]

	def hotbar_start(self):
		return self.window.hotbar_slots()[0].slot_nr

@pl_announce('Inventory')
class InventoryPlugin:
	def __init__(self, ploader, settings):
		self.clinfo = ploader.requires('ClientInfo')
		self.event = ploader.requires('Event')
		self.net = ploader.requires('Net')
		self.timer = ploader.requires('Timers')
		self.inventory = InventoryCore(self.net, self.send_click)
		ploader.provides('Inventory', self.inventory)

		# Inventory events
		ploader.reg_event_handler(
			'PLAY<Held Item Change', self.handle_held_item_change)
		ploader.reg_event_handler(
			'PLAY<Set Slot', self.handle_set_slot)
		ploader.reg_event_handler(
			'PLAY<Window Items', self.handle_window_items)
		ploader.reg_event_handler(
			'PLAY<Window Property', self.handle_window_prop)
		ploader.reg_event_handler(
			'PLAY<Confirm Transaction', self.handle_confirm_transaction)
		ploader.reg_event_handler(
			'PLAY<Open Window', self.handle_open_window)
		ploader.reg_event_handler(
			'PLAY<Close Window', self.handle_close_window)
		# also register to serverbound, as server does not send Close Window when we do
		ploader.reg_event_handler(
			'PLAY>Close Window', self.handle_close_window)

		# click sending
		self.action_id = 0
		self.last_click = None  # stores the last click action for confirmation

	def handle_held_item_change(self, event, packet):
		self.inventory.selected_slot = packet.data['slot']
		self.event.emit('inv_held_item_change', packet.data)

	def handle_open_window(self, event, packet):
		InvNew = inv_types[packet.data['inv_type']]
		self.inventory.window = InvNew(add_slots=self.inventory.window.slots, **packet.data)
		self.event.emit('inv_open_window', {'window': self.inventory.window})

	def handle_close_window(self, event, packet):
		closed_window = self.inventory.window
		self.inventory.window = InventoryPlayer(add_slots=closed_window.slots)
		self.event.emit('inv_close_window', {'window': closed_window})

	def handle_set_slot(self, event, packet):
		self.set_slot(packet.data['window_id'], packet.data['slot'], packet.data['slot_data'])

	def handle_window_items(self, event, packet):
		window_id = packet.data['window_id']
		for slot_nr, slot_data in enumerate(packet.data['slots']):
			self.set_slot(window_id, slot_nr, slot_data)

	def set_slot(self, window_id, slot_nr, slot_data):
		if window_id == INV_WINID_CURSOR and slot_nr == INV_SLOT_NR_CURSOR:
			slot = self.inventory.cursor_slot = SlotCursor(**slot_data)
		elif window_id == self.inventory.window.window_id:
			slot = self.inventory.window.slots[slot_nr] = Slot(self.inventory.window, slot_nr, **slot_data)
		else:
			raise ValueError('Unexpected window ID (%i) or slot_nr (%i)' % (window_id, slot_nr))
		self.emit_set_slot(slot)

	def emit_set_slot(self, slot):
		self.event.emit('inv_set_slot', {'slot': slot})

	def handle_window_prop(self, event, packet):
		self.inventory.window.properties[packet.data['property']] = packet.data['value']
		self.event.emit('inv_win_prop', packet.data)

	def handle_confirm_transaction(self, event, packet):
		(click, response), self.last_click = self.last_click, None
		accepted = packet.data['accepted']
		if accepted:
			# TODO check if the wrong window/action ID was confirmed, never occured during testing
			# update inventory, because 1.8 server does not send slot updates after successful clicks
			click.success(self.inventory, self.emit_set_slot)
			self.event.emit(response, {'accepted': accepted, 'click': click})
		else:  # click not accepted
			# confirm that we received this packet
			packet.new_ident('PLAY>Confirm Transaction')
			self.net.push(packet)
			# 1.8 server will re-send all slots now
			def cb():
				self.event.emit(response, {'accepted': accepted, 'click': click})
			self.timer.reg_event_timer(0.5, cb, runs=1)

	def send_click(self, click):
		"""
		Returns unique response event name if the
		click could be sent, None otherwise.
		"""
		# only send if previous packet got confirmed
		if self.last_click:
			return None
		packet = click.get_packet(self.inventory)
		if not packet:
			return None
		packet['window_id'] = self.inventory.window.window_id
		packet['action'] = self.action_id
		self.action_id += 1
		response = self.event.get_unique_response_event()
		self.last_click = (click, response)
		self.net.push_packet('PLAY>Click Window', packet)
		return response
