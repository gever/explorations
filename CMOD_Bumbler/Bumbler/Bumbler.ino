// Bumbler.ino
// Simple animatronic toy controlled by an Arduino Nano
// Features a vibration sensor (input) and PWM motor control (output)

const int VIBRATION_SENSOR_PIN = 2; // Digital input from vibration sensor
const int MOTOR_PWM_PIN = 3;        // PWM output to motor driver
volatile bool vibrated = false;

void detectVibration() { vibrated = true; }

void setup() {
  // Initialize serial communication for debugging
  Serial.begin(115200);

  // Trigger when the pin goes from HIGH to LOW (FALLING)
  attachInterrupt(digitalPinToInterrupt(VIBRATION_SENSOR_PIN), detectVibration,
                  FALLING);

  // Using INPUT_PULLUP: Pin is HIGH normally, LOW when vibration occurs
  pinMode(VIBRATION_SENSOR_PIN, INPUT_PULLUP);

  // Ensure the motor is off initially
  pinMode(MOTOR_PWM_PIN, OUTPUT);
  analogWrite(MOTOR_PWM_PIN, 0);

  Serial.println("Bumbler initialized.");
}

void loop() {
  if (vibrated) {
    vibrated = false;
    Serial.println("Vibration detected! Activating motor.");

    // Turn on the motor at 50% duty cycle (127 out of 255)
    analogWrite(MOTOR_PWM_PIN, 127);

    // Keep motor running for a short duration (e.g., 1 second)
    delay(1000);

    // Turn off the motor
    analogWrite(MOTOR_PWM_PIN, 0);
    Serial.println("Motor deactivated.");
  }

  // Small delay for stability
  delay(10);
}
