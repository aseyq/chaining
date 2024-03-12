from otree.api import *
import random
import time

doc = """
Chaining
"""


class C(BaseConstants):
    NAME_IN_URL = 'chaining'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1

    CHAIN_LENGTH = 5
    NUM_CHAINS = 3
    # WAITPAGE_REFRESH_INTERVAL is set on JS in ChainWait.html
    NOMATCH_TIMEOUT = 3 * 60

class Subsession(BaseSubsession):
    num_waiting = models.IntegerField(initial=0)

def creating_session(subsession):
    print('Creating session...')
    #print_chains_status(subsession)

    for p in subsession.get_players():
        p.participant.chain_code = None
        p.participant.vars['generation'] = None
        p.participant.vars['time_started'] = None


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    chain = models.StringField()
    generation = models.IntegerField()
    rejected = models.BooleanField(initial=False)
    dropped = models.BooleanField(initial=False)


class ChainWait(WaitPage):
    group_by_arrival_time = True
    template_name = 'chaining/ChainWait.html'
    
    def is_displayed(player):
        return player.round_number == 1
    
    def app_after_this_page(player, upcoming_apps):
        if player.dropped:
            return "timedout"
        
        if player.rejected:
            return "nomatch"
        
        if player.participant.chain_code is None:
            return "nomatch"
    
def group_by_arrival_time_method(subsession, waiting_players):
    for player in waiting_players:
        if waiting_too_long(player):
            player.rejected = True
            subsession.num_waiting = len(waiting_players) - 1
            return [player]

    if len(waiting_players) >= 1:
        first_in_line = waiting_players[0]

        assigned_player = chain_assignement(first_in_line) # returns None if no chain is available

        if assigned_player is None:
            subsession.num_waiting = len(waiting_players)
            return None
        else:
            subsession.num_waiting = len(waiting_players) - 1
            return [assigned_player]
        


def waiting_too_long(player):
    if player.participant.vars['time_started'] is None:
        player.participant.vars['time_started'] = time.time()
        return False

    time_spent = time.time() - player.participant.vars['time_started']
    print('Time waiting:', time_spent, 'for player', player.participant.code)
    return time_spent > C.NOMATCH_TIMEOUT



class MainTask(Page):
    timeout_seconds = 30

    # def is_displayed(player):
    #     if player.rejected:
    #         return False

    #     if player.dropped:
    #         return False
        
    #     if player.chain is None:
    #         return False
        
        

    def vars_for_template(player):
        #print_chains_status(player.subsession)
        pass
    
    def before_next_page(player, timeout_happened):
        my_chain = get_my_chain(player)

        if timeout_happened:
            player.dropped = True
            drop_me_from_chain(player, my_chain)
            return

        complete_player(player, my_chain)

    def app_after_this_page(player, upcoming_apps):
        if player.dropped:
            return "timedout"
        
        if player.rejected:
            return "nomatch"
        
        if player.participant.chain_code is None:
            return "nomatch"

class PlayerFinished(Page):
    pass
        

page_sequence = [
                 ChainWait,
                 #BeforeChain, 
                 MainTask, 
                 PlayerFinished
                 ]



class ChainModel(ExtraModel):
    subsession = models.Link(Subsession)
    chain_code = models.StringField()
    available = models.BooleanField()
    full = models.BooleanField(initial=False)
    complete = models.BooleanField(initial=False)

    for c in range(1, C.CHAIN_LENGTH + 1):
        locals()[f'p{c}'] = models.Link(Player)
        locals()[f'id{c}'] = models.IntegerField()
        locals()[f'participant{c}'] = models.StringField()
        locals()[f'pdone{c}'] = models.BooleanField(initial=False)
        locals()[f'pconfig{c}'] = models.LongStringField()

    def test(__self__):
        print('test')





# ==== Chain stuff ===
def chains_full(subsession):
    return len(ChainModel.filter(subsession=subsession, full=True)) == C.NUM_CHAINS

def chain_assignement(player):
    if chains_full(player.subsession):
        print('All chains are full')
        player.rejected = True
        return player

    print("chiain assignement")
    available_chains = ChainModel.filter(subsession=player.subsession, available=True)
    all_chains = ChainModel.filter(subsession=player.subsession)

    if available_chains != []:
        print('Adding player to chain')
        add_player_to_chain(player, available_chains[0])
        return player
    else:
        if available_chains == [] and len(all_chains) < C.NUM_CHAINS:
            print('Creating new chain')
            create_chain_for_me(player)
            return player
        else:
            #print_chains_status(player.subsession)
            return None


def custom_export(players):
    # Export the ExtraModel of ChainModel

    p_strings = []
    id_strings = []
    participant_strings = []
    config_strings = []

    for c in range(1, C.CHAIN_LENGTH + 1):
        id_strings.append(f'id{c}')
        participant_strings.append(f'participant{c}')
        config_strings.append(f'pconfig{c}')


    columns = ['session_code', 'chain_code', 'available', 'full', 'complete'] + id_strings + participant_strings + config_strings

    yield columns

    chains = ChainModel.filter()

    for chain in chains:
        row = [chain.subsession.session.code, chain.chain_code, chain.available, chain.full, chain.complete] 
        for i in id_strings:
            row.append(getattr(chain, i))
        for p in participant_strings:
            row.append(getattr(chain, p))
        for c in config_strings:
            row.append(getattr(chain, c))

        yield row


    
def filter_chain_by_code(chain_code=None):
    # really inefficient
    all_chains = ChainModel.filter()
    filtered_chains = [chain for chain in all_chains if chain.chain_code == chain_code]
    return filtered_chains

def get_my_chain(player):
    my_chain_code = player.participant.chain_code
    my_chain = filter_chain_by_code(my_chain_code)
    return my_chain[0]



def create_new_name():
    return ''.join(random.choice('ABCDEFGHIJKLMNOPQRSTUVWYZ') for _ in range(5))

def create_chain_for_me(player):
    chain_code = create_new_name()

    chain = ChainModel.create(subsession=player.subsession, chain_code = chain_code, available = False, p1=player, id1=player.id_in_subsession, participant1=player.participant.code)

    print("Chain created for player", player.participant.code, "with code", chain_code)
    set_attributes(player, chain, 1)


def add_player_to_chain(player, chain):
    # find the first p among p1, p2, ... that is not set
    available_gen = None
    
    for gen in range(1, C.CHAIN_LENGTH + 1):
        if getattr(chain, f'p{gen}') == None:
            available_gen = gen
            break


    setattr(chain, f'p{available_gen}', player)
    setattr(chain, f'id{available_gen}', player.id_in_subsession)
    setattr(chain, f'participant{available_gen}', player.participant.code)

    chain.available = False

    if available_gen == C.CHAIN_LENGTH:
        chain.full = True
        print('Chain', chain.chain_code, 'is full')

    set_attributes(player, chain, available_gen)

    print('Added player', player.participant.code, 'to chain', chain.chain_code, 'as p',available_gen )


def set_attributes(player, chain, generation):
    player.participant.chain_code = chain.chain_code
    player.participant.generation = generation

    player.chain = chain.chain_code
    player.generation = generation



def complete_player(player, chain):
    # mark me as done
    setattr(chain, f'pdone{player.participant.generation}', True)


    if player.participant.generation < C.CHAIN_LENGTH:
        chain.available = True
        print('Chain', chain.chain_code, 'is available for the next participant')
    else:
        print('Chain', chain.chain_code, 'is complete')
        chain.complete = True
        chain.available = False # this is not necessary, but it's good to be explicit

    #print_chains_status(player.subsession)


def drop_me_from_chain(player, chain):
    my_location = player.participant.generation
    setattr(chain, f'p{my_location}', None)
    setattr(chain, f'id{my_location}', None)
    setattr(chain, f'participant{my_location}', None)

    chain.full = False
    chain.available = True

    player.participant.chain_code = None
    player.participant.generation = None
    player.dropped = True
    print('Dropped player', player.participant.code, 'from chain', chain.chain_code)

    #print_chains_status(player.subsession)


def get_status_of_chain(chain):

    # example status: 
    # {'chain_code': 'ABCD', 'full': False, 'complete': False, 'available': True, 'players': [2, 2, 1, 0, 0]}
    status = dict()
    status['chain_code'] = chain.chain_code
    status['full'] = chain.full
    status['complete'] = chain.complete
    status['available'] = chain.available

    players = []
    player_ids = []
   
   # 0 if not set but available, 1 if set but not done, 2 if set and done
    first_available = True
    for i in range(1, C.CHAIN_LENGTH + 1):
        if getattr(chain, f'p{i}') == None:
            if chain.available and first_available:
                players.append(0)
                first_available = False
            else:
                players.append(-1)
        else:
            if getattr(chain, f'pdone{i}'):
                players.append(2)
            else:
                players.append(1)

    for i in range(1, C.CHAIN_LENGTH + 1):
        player_ids.append(getattr(chain, f'id{i}'))

    status['players'] = zip(players, player_ids)
    return status

def print_chains_status(subsession):
    print("\n" * 1)
    print_table_header()
    print_table_separator()

    for chain in ChainModel.filter(subsession=subsession):
        print_chain_info(chain)

    print_uncreated_chains(subsession)


    print_table_separator()
    print_legend()
    print("\n" * 1) 
    print_summary(subsession)
    print_num_waiting(subsession)

    print("\n" * 1)

def print_legend():
    print("■ - Completed,  ◧ - In progress, ◰ - Available slot,  ☐ - Empty")
    
def print_table_header():
    chain_length_headers = " ".join([f"{i}  " for i in range(1, C.CHAIN_LENGTH + 1)])
    string_title = "{:<10} | {:<8} | {:<10} | {:<8} | {}".format("CHAIN", "FULL", "COMPLETE", "AVAILABLE", chain_length_headers)
    print(string_title)


def print_table_separator():
    print("-" * (get_table_width() + 2))


def print_chain_info(chain):
    status = get_status_of_chain(chain)
    players_boxes = get_players_boxes(status)

    chain_info = "{:<10} | {:<8} | {:<10} | {:<9} | {}".format(
        chain.chain_code,
        "Yes" if status['full'] else "No",
        "Yes" if status['complete'] else "No",
        "Yes" if status['available'] else "No",
        " ".join("  ").join(players_boxes)
    )
    print(chain_info)


def get_players_boxes(status):
    players_boxes = []

    # case 
    for i, status in enumerate(status['players']):
        if status[0] == 0:
            players_boxes.append("◰")
        elif status[0] == -1:
            players_boxes.append("☐")
        elif status[0] == 1:
            players_boxes.append("◧")
        elif status[0] == 2:
            players_boxes.append("■")

    return players_boxes


def print_uncreated_chains(subsession):
    uncreated_chains = C.NUM_CHAINS - len(ChainModel.filter(subsession=subsession))
    
    for _ in range(uncreated_chains):
        boxes = ["◰  " if i == 0 else "☐  " for i in range(C.CHAIN_LENGTH)]
        print("{:<10} | {:<8} | {:<10} | {:<9} | {}".format("-" * 5, "-" * 4, "-" * 6, "-" * 5, " ".join(boxes)))


def get_table_width():
    return len("{:<10} | {:<8} | {:<10} | {:<8} | {}".format("", "", "", "", " ".join(["  " for _ in range(C.CHAIN_LENGTH)])))

def get_summary_text(subsession):
    expected_chains = C.NUM_CHAINS
    total_chains = len(ChainModel.filter(subsession=subsession))
    available_chains = len(ChainModel.filter(subsession=subsession, available=True))
    full_chains = len(ChainModel.filter(subsession=subsession, full=True))
    uncreated_chains = expected_chains - total_chains
    spots_available = uncreated_chains + available_chains

    return f"Target: {expected_chains} | Total: {total_chains} | Expecting: {available_chains} | Full: {full_chains} | Uncreated: {uncreated_chains} | SLOTS: {spots_available}"


def print_summary(subsession):
    print(get_summary_text(subsession))

def print_num_waiting(subsession):
    print("=============== Number of waiting players: ", subsession.num_waiting, "==================")


def vars_for_admin_report(subsession):
    chain_statuses = dict()
    for chain in ChainModel.filter(subsession=subsession):
        chain_statuses[chain.chain_code] = get_status_of_chain(chain)

    expected_chains = C.NUM_CHAINS
    total_chains = len(ChainModel.filter(subsession=subsession))
    available_chains = len(ChainModel.filter(subsession=subsession, available=True))
    full_chains = len(ChainModel.filter(subsession=subsession, full=True))
    uncreated_chains = expected_chains - total_chains
    spots_available = uncreated_chains + available_chains

    return dict(chain_statuses=chain_statuses, num_waiting=subsession.num_waiting, expected_chains=expected_chains, total_chains=total_chains, available_chains=available_chains, full_chains=full_chains, uncreated_chains=uncreated_chains, spots_available=spots_available, uncreated_chains_iterable = range(uncreated_chains), num_gens = range(C.CHAIN_LENGTH))