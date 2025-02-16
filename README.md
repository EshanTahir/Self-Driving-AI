# Self-Driving-AI
Self-driving car created using NEAT genetic algorithm. Able to simulate real life conditions in a 2-dimentional enviroment.

Update: The physics could use fine tuning. There seems to be hidden bugs causing the model not to be able to train well in this form, except for rare outliers. Can be fixed by modifying or replacing physics, see:
https://rmgi.blog/pygame-2d-car-tutorial.html
https://asawicki.info/Mirror/Car%20Physics%20for%20Games/Car%20Physics%20for%20Games.html 

Planned remake in Rust using Bevy, Shipyard, and Rapier. Splitting training into a headless program with the AI and car physics implemented from scratch, and streaming the outputs to another and displaying using Bevy.
