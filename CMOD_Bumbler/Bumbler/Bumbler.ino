// Bumbler.ino
// Simple animatronic toy controlled by an Arduino Nano
// Features a vibration sensor (input) and PWM motor control (output)

const int VIBRATION_SENSOR_PIN = 2; // Digital input from vibration sensor
const int MOTOR_PWM_PIN = 10; // PWM output to motor driver speed (ENA/ENB)
const int MOTOR_DIR1_PIN = 9; // Motor direction pin 1 (IN1/IN3)
const int MOTOR_DIR2_PIN = 8; // Motor direction pin 2 (IN2/IN4)
volatile bool vibrated = false;
bool rngSeeded = false;

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
  pinMode(MOTOR_DIR1_PIN, OUTPUT);
  pinMode(MOTOR_DIR2_PIN, OUTPUT);

  analogWrite(MOTOR_PWM_PIN, 0);
  digitalWrite(MOTOR_DIR1_PIN, LOW);
  digitalWrite(MOTOR_DIR2_PIN, LOW);

  Serial.println("Bumbler initialized.");
}

void loop() {
  if (vibrated) {
    vibrated = false;
    Serial.println("Vibration detected! Activating motor.");

    if (!rngSeeded) {
      randomSeed(millis());
      rngSeeded = true;
      Serial.println("RNG Seeded.");
    }

    // Set motor direction
    if (random(0, 2) == 0) {
      digitalWrite(MOTOR_DIR1_PIN, HIGH);
      digitalWrite(MOTOR_DIR2_PIN, LOW);
    } else {
      digitalWrite(MOTOR_DIR1_PIN, LOW);
      digitalWrite(MOTOR_DIR2_PIN, HIGH);
    }

    // Turn on the motor at 50% duty cycle (127 out of 255)
    analogWrite(MOTOR_PWM_PIN, 127);

    // Keep motor running for a random duration between 3/4 and 1.5 seconds
    long runDuration = random(750, 1500);
    delay(runDuration);

    // Turn off the motor
    analogWrite(MOTOR_PWM_PIN, 0);
    digitalWrite(MOTOR_DIR1_PIN, LOW);
    digitalWrite(MOTOR_DIR2_PIN, LOW);
    Serial.println("Motor deactivated.");
  }

  // Small delay for stability
  delay(1500);
}
