# switchboardui

Switchboardui is a Python-based MQTT client with GUI designed to subscribe to provided MQTT broker and either 
act as a fallback in case of a hardware switchboard malfunction 
or an easier way to test switchboard dependent parts of the launchpad nad rocket itself.
## Features

- Subscribe to broker on port
- Listen to switchboard messages on all topics
- Send messages on switchboard topics

## Getting Started

### Prerequisites

Ensure you have the following installed:

- Python 3.10+
- `pip` (Python package installer)

### Setting Up the Environment

1. **Clone the Repository**

   Clone the repository to your local machine:

   ```bash
   git clone https://gitlab.com/putrocketlab/it/groundstation/missioncontrolcenter/switchboardui
   cd switchboardui
   ```

2. **Create a Virtual Environment**

   It's recommended to use a virtual environment to manage dependencies. Run the following command to create a virtual
   environment:

   ```bash
   python -m venv venv
   ```

3. **Activate the Virtual Environment**

   Activate the virtual environment using the appropriate command for your operating system:

    - **Windows:**

      ```bash
      venv\Scripts\activate
      ```

    - **macOS and Linux:**

      ```bash
      source venv/bin/activate
      ```

4. **Install Required Packages**

   With the virtual environment activated, install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
   And the complimentary python-utils library with all the proto files:
   ```bash
   pip install python-utils==3.3.4 --extra-index-url https://repo.rocketlab.pl/repository/python/simple
   ```
   However, you will need a login and a password to access this one. 
   Only Rocketlab members have access. If you are one of them and need it - ask for it on our discord.

## Usage

1. Configure the `config.json` file by defining switch names for each switchboard (see **Configuration**).
2. Run the application:
   ```bash
   python main.py
   ```
   
3. In the window, enter the IP and port of your MQTT broker, then click Lock in setup.

4. Once connected, the switches become active:

   * Clicking a button toggles its state between 0 and 1.
   * Hold behaviour enables press-and-hold activation mode.
   * On top of that, there is a background listener that records the last value published to the broker on each 
   switchboard topic

5. Switch states are published as a 12-bit integer to topics:
   switchboard-{N}/out (e.g., switchboard-1/out), where N is the board number.

6. Buttons:

   * Reset switches and setup – disconnects from the broker and resets all switches and their behaviour.

   * Apply cached states – restores the last received states from the broker.

   * Save switch names to config – saves current switch names into config.json.

### Configuration

The application expects a config.json file with a switch_names section.
Each board (sb_1, sb_2, …) has to define switch names as a dictionary: sw_{index} → name
```json
{
  "switch_names": {
    "sb_1": {
      "sw_0": "Switch_0",
      "sw_1": "Switch_1",
      [...]
      "sw_11": "Switch_11"
    },
    "sb_2": {
      "sw_0": "Switch_0",
      "sw_1": "Switch_1",
      [...]
      "sw_11": "Switch_11"
    },
     [...]
  }
}
```

### Deactivating the Virtual Environment

When you're done working on the project, deactivate the virtual environment by running:

```bash
deactivate
```

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
