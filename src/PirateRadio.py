#!/usr/bin/env python
# Pirate Radio
# Author: Wynter Woods (Make Magazine)

import os
import sys
import subprocess
import configparser
import re
import random
import threading
import time
import csv
import random


fm_process = None
on_off = ["off", "on"]

frequency = 87.9
shuffle = False
repeat_all = True
merge_audio_in = False
play_stereo = True

music_pipe_r, music_pipe_w = os.pipe()
microphone_pipe_r, microphone_pipe_w = os.pipe()

CSV_FILE_PATH = "/pirateradio/song_attributes.csv"
WAITING_FILE = "/pirateradio/waiting.mp3"

def main():
    play_waiting()
    daemonize()
    setup()
    files, announce_file_list = build_file_list()
    ensure_csv_up_to_date(files)
    song_data = load_song_data()
    ordered_file_list = reorder_file_list(files, song_data)
    ensure_csv_up_to_date(files)    
    stop_waiting_after_minimum_time()
    if repeat_all:
        while True:
            play_songs(ordered_file_list, announce_file_list)
            ordered_file_list = reorder_file_list(files, song_data)            
    else:
        play_songs(ordered_file_list, announce_file_list)
    return 0
    
    
    

def extend_list_to_length(lst, target_length):
    if not lst:  # Prevents infinite loop if lst is empty
        return lst
    extended_list = lst.copy()
    while len(extended_list) < target_length:
        extended_list.extend(random.sample(lst, min(len(lst), target_length - len(extended_list))))
    return extended_list

def build_file_list():
    file_list = []
    announce_file_list = []
    for root, folders, files in os.walk("/pirateradio"):
        folders.sort()
        files.sort()
        for filename in files:
            if re.search(r".(aac|mp3|wav|flac|m4a)$", filename):
                full_path = os.path.join(root, filename)
                if '/pirateradio/announce/' in full_path:
                    announce_file_list.append(full_path)
                else:
                    file_list.append(full_path)
                    
    max_length = max(len(file_list), len(announce_file_list))
    file_list = extend_list_to_length(file_list, max_length)
    announce_file_list = extend_list_to_length(announce_file_list, max_length)
    return file_list, announce_file_list

def ensure_csv_up_to_date(file_list):
    if not os.path.exists(CSV_FILE_PATH):
        create_csv(file_list)
    else:
        update_csv(file_list)

def create_csv(file_list):
    with open(CSV_FILE_PATH, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        for song in file_list:
            csvwriter.writerow([song, 50, 50])

def update_csv(file_list):
    with open(CSV_FILE_PATH, 'r', newline='') as csvfile:
        csvreader = csv.reader(csvfile)
        existing_songs = {rows[0]: (rows[1], rows[2]) for rows in csvreader}
    
    with open(CSV_FILE_PATH, 'w', newline='') as csvfile:
        csvwriter = csv.writer(csvfile)
        for song in file_list:
            if song in existing_songs:
                csvwriter.writerow([song, existing_songs[song][0], existing_songs[song][1]])
            else:
                csvwriter.writerow([song, 50, 50])

def jitter_value(value):
    # Apply random integer jitter between -10 and 10
    value += random.randint(-10, 10)
    
    # Apply random percentage jitter between -10% and +10% of the value
    percentage_jitter = random.uniform(-0.1, 0.1) * value
    value += int(percentage_jitter)
    
    # Cap the value to be at least 0
    if value < 0:
        value = 0
    
    # Cap the value to be at most 100
    if value > 100:
        value = 100
    
    return value
    
    
def load_song_data():
    song_data = {}
    with open(CSV_FILE_PATH, 'r', newline='') as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            song = row[0]
            energy = int(row[1])
            organics = int(row[2])
            # Apply jitter and cap values for energy and organics
            energy = jitter_value(energy)
            organics = jitter_value(organics)
            song_data[song] = (energy, organics)
    return song_data


def reorder_file_list(file_list, song_data):
    """
    Reorders the file list based on the song attributes (energy, organics) to play songs with similar attributes consecutively.
    """
    if not file_list:
        return []

    # Shuffle the file list to introduce randomness
    random.shuffle(file_list)

    # Remove any files not present in the song_data dictionary
    file_list = [song for song in file_list if song in song_data]

    # If the file list is empty after filtering, return early
    if not file_list:
        return []

    # Start the ordered list with the first song
    current_song = file_list.pop(0)
    ordered_list = [current_song]

    while file_list:
        # Get current song's attributes
        current_energy, current_organics = song_data.get(current_song, (50, 50))

        # Find the next song with the closest attributes
        nearest_song = None
        nearest_distance = float('inf')

        for song in file_list:
            # Safely get the attributes with default values
            energy, organics = song_data.get(song, (50, 50))
            distance = abs(energy - current_energy) + abs(organics - current_organics)

            if distance < nearest_distance:
                nearest_distance = distance
                nearest_song = song

        # If no nearest song is found, break to prevent infinite loop
        if nearest_song is None:
            break

        # Add the nearest song to the ordered list and update current_song
        ordered_list.append(nearest_song)
        file_list.remove(nearest_song)
        current_song = nearest_song

    return ordered_list

def play_songs(file_list, announce_file_list):
    print("Playing songs to frequency ", str(frequency))
    print("Shuffle is " + on_off[shuffle])
    print("Repeat All is " + on_off[repeat_all])
    
    if shuffle:
        random.shuffle(file_list)
        random.shuffle(announce_file_list)

    with open(os.devnull, "w") as dev_null:
        for song_file, announce_file in zip(file_list, announce_file_list):
            print("Playing announcement ", announce_file)
            subprocess.call(["ffmpeg", "-i", announce_file, "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "2" if play_stereo else "1", "-ar", "44100", "-"], stdout=music_pipe_w, stderr=dev_null)
            print("Playing song ", song_file)
            subprocess.call(["ffmpeg", "-i", song_file, "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "2" if play_stereo else "1", "-ar", "44100", "-"], stdout=music_pipe_w, stderr=dev_null)

def read_config():
    global frequency
    global shuffle
    global repeat_all
    global play_stereo
    try:
        config = configparser.ConfigParser()
        config.read("/pirateradio/pirateradio.config")
    except:
        print("Error reading from config file.")
    else:
        play_stereo = config.getboolean("pirateradio", 'stereo_playback', fallback=True)
        frequency = config.getfloat("pirateradio", 'frequency', fallback=87.9)
        shuffle = config.getboolean("pirateradio", 'shuffle', fallback=False)
        repeat_all = config.getboolean("pirateradio", 'repeat_all', fallback=False)

def daemonize():
    fpid = os.fork()
    if fpid != 0:
        sys.exit(0)

def setup():
    global frequency
    read_config()
    run_pifm()

def run_pifm(use_audio_in=False):
    global fm_process
    with open(os.devnull, "w") as dev_null:
        fm_process = subprocess.Popen(["/root/pifm", "-", str(frequency), "44100", "stereo" if play_stereo else "mono"], stdin=music_pipe_r, stdout=dev_null)

def record_audio_input():
    return subprocess.Popen(["arecord", "-fS16_LE", "--buffer-time=50000", "-r", "44100", "-Dplughw:1,0", "-"], stdout=microphone_pipe_w)


def open_microphone():
    global fm_process
    audio_process = None
    if os.path.exists("/proc/asound/card1"):
        audio_process = record_audio_input()
        run_pifm(merge_audio_in)
    else:
        run_pifm()

def play_waiting():
    global waiting_process
    waiting_process = subprocess.Popen(["ffmpeg", "-re", "-i", WAITING_FILE, "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "2" if play_stereo else "1", "-ar", "44100", "-"], stdout=music_pipe_w, stderr=subprocess.DEVNULL)

def stop_waiting_after_minimum_time():
    global waiting_process
    time.sleep(60)  # Ensure the waiting song plays for at least 60 seconds
    if waiting_process:
        waiting_process.terminate()

if __name__ == "__main__":
    main()

