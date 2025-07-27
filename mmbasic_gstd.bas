' This code was generated in collaboration with Google Gemini, on 2025-07-26
' An implementation of Galactic Space Tortoise Doctor

' --- Runtime Options ---
OPTION EXPLICIT ' require all variables to be declared
OPTION DEFAULT NONE ' do not supply default values for uninitialized variables

' --- Constants and Global Variables ---
CONST SCREEN_WIDTH = 320
CONST SCREEN_HEIGHT = 320
CONST LAUNCH_X = 10 ' X position of the launch platform
CONST PLATFORM_HEIGHT = 20 ' Height of the launch platform
CONST ROCKET_INITIAL_SPEED_X = 5 ' Initial horizontal speed of rocket
CONST ROCKET_MASS = 1 ' Arbitrary mass for the rocket
CONST PLANET_RADIUS = 10
CONST PLANET_RADIUS_SQ = PLANET_RADIUS * PLANET_RADIUS
CONST MIN_DIST_SQ = (PLANET_RADIUS + 5) * (PLANET_RADIUS + 5)
CONST NUM_PLANETS = 5
CONST GRAV_CONSTANT = 50 ' Tuning constant for gravitational strength

DIM INTEGER planets(NUM_PLANETS, 4) ' x, y, status (0=infected, 1=vaccinated), color
DIM INTEGER currPlatformY
DIM FLOAT rocketX, rocketY, rocketVelX, rocketVelY
DIM INTEGER rocketActive
DIM INTEGER infectedPlanetCount
DIM STRING key$

' --- Colors ---
' Define custom color values for MMBASIC using COL_ prefix
CONST COL_ORANGE = RGB(255, 128, 0)
CONST COL_GREEN = RGB(0, 255, 0)
CONST COL_BLACK = RGB(0, 0, 0)
CONST COL_BLUE = RGB(0, 0, 255)


' --- Game Initialization ---
SUB GameInit
    CLS COL_BLACK ' Clear screen to black
    currPlatformY = SCREEN_HEIGHT / 2 ' Initial platform position
    rocketActive = 0 ' No rocket launched initially
    infectedPlanetCount = NUM_PLANETS

    ' Initialize planets
    LOCAL INTEGER i
    FOR i = 0 TO NUM_PLANETS - 1
        ' Ensure planets are not too close to launch platform or edges
        planets(i, 0) = INT(RND * (SCREEN_WIDTH - 2 * PLANET_RADIUS - LAUNCH_X - 60)) + LAUNCH_X + 60 ' X position
        planets(i, 1) = INT(RND * (SCREEN_HEIGHT - 2 * PLANET_RADIUS)) + PLANET_RADIUS ' Y position
        planets(i, 2) = 0 ' Infected
        planets(i, 3) = COL_ORANGE ' Initial color
    NEXT i
END SUB

' --- Drawing Routines ---
SUB DrawPlatform(C%)
    COLOR C%
    LINE 0, currPlatformY, 0, currPlatformY + PLATFORM_HEIGHT
    LINE 0, currPlatformY, LAUNCH_X, currPlatformY + (PLATFORM_HEIGHT/2)
    LINE 0, currPlatformY + PLATFORM_HEIGHT, LAUNCH_X, currPlatformY + (PLATFORM_HEIGHT/2)
END SUB

SUB DrawRocket
    IF rocketActive THEN
        PIXEL rocketX, rocketY, COL_BLUE ' single blue pixel
    END IF
END SUB

SUB DrawPlanets
    LOCAL INTEGER i
    FOR i = 0 TO NUM_PLANETS - 1
        COLOR planets(i, 3) ' Use planet's specific color
        CIRCLE planets(i, 0), planets(i, 1), PLANET_RADIUS
    NEXT i
END SUB

' --- Game Logic ---
SUB UpdatePlatform(delta%)
    DrawPlatform(COL_BLACK)
    currPlatformY = currPlatformY + delta% ' Update position once
    
    ' Enforce boundaries
    IF currPlatformY < 10 THEN
        currPlatformY = 10
    ELSEIF currPlatformY > SCREEN_HEIGHT - PLATFORM_HEIGHT THEN
        currPlatformY = SCREEN_HEIGHT - PLATFORM_HEIGHT
    END IF
    
    DrawPlatform(COL_BLUE)
END SUB

SUB LaunchRocket
    IF NOT rocketActive THEN
        rocketX = LAUNCH_X + 1 ' Start just to the right of the platform
        rocketY = currPlatformY + PLATFORM_HEIGHT / 2 ' Middle of the platform
        rocketVelX = ROCKET_INITIAL_SPEED_X ' Initial horizontal velocity
        rocketVelY = 0 ' Initial vertical velocity
        rocketActive = 1
    END IF
END SUB

SUB UpdateRocket
    IF rocketActive THEN
        LOCAL FLOAT totalForceX, totalForceY
        LOCAL FLOAT planetX, planetY, distSq, dist, forceMag
        LOCAL FLOAT dirX, dirY
    
        totalForceX = 0
        totalForceY = 0

        LOCAL INTEGER i
        FOR i = 0 TO NUM_PLANETS - 1
            planetX = planets(i, 0)
            planetY = planets(i, 1)

            dirX = planetX - rocketX
            dirY = planetY - rocketY
            distSq = dirX * dirX + dirY * dirY

            ' OPTIMIZED: Use pre-calculated constant
            IF distSq < MIN_DIST_SQ THEN
                distSq = MIN_DIST_SQ
            END IF

            dist = SQR(distSq)

            dirX = dirX / dist
            dirY = dirY / dist

            forceMag = GRAV_CONSTANT * PLANET_RADIUS / distSq

            totalForceX = totalForceX + (dirX * forceMag)
            totalForceY = totalForceY + (dirY * forceMag)
        NEXT i

        ' Apply acceleration (F = ma => a = F/m)
        rocketVelX = rocketVelX + (totalForceX / ROCKET_MASS)
        rocketVelY = rocketVelY + (totalForceY / ROCKET_MASS)

        ' Update position
        rocketX = rocketX + rocketVelX
        rocketY = rocketY + rocketVelY

        ' Check for out of bounds
        IF rocketX < 0 OR rocketX > SCREEN_WIDTH OR rocketY < 0 OR rocketY > SCREEN_HEIGHT THEN
            rocketActive = 0
            DrawPlanets
            EXIT SUB
        END IF

        ' Check for collision with planets (only vaccinates infected ones)
        LOCAL FLOAT dx, dy
        FOR i = 0 TO NUM_PLANETS - 1
            dx = rocketX - planets(i, 0)
            dy = rocketY - planets(i, 1)
                
            IF (dx*dx + dy*dy) < PLANET_RADIUS_SQ THEN ' collision
                IF planets(i, 2) = 0 THEN
                    planets(i, 2) = 1
                    planets(i, 3) = COL_GREEN
                    infectedPlanetCount = infectedPlanetCount - 1
                    COLOR COL_GREEN
                    CIRCLE planets(i, 0), planets(i, 1), PLANET_RADIUS
                    rocketActive = 0
                END IF
                EXIT SUB
            END IF
        NEXT i

        DrawRocket
    END IF
END SUB

' --- Main Game Loop ---
Randomize
GameInit
DrawPlatform(COL_BLUE)
DrawPlanets

DO
    key$ = INKEY$
    IF key$ = CHR$(128) THEN
        UpdatePlatform -5
    ELSEIF key$ = CHR$(129) THEN
        UpdatePlatform 5
    ELSEIF key$ = "p" THEN
        LaunchRocket
    END IF

    UpdateRocket

    IF infectedPlanetCount = 0 THEN
        PRINT @(80,160) "ALL PLANETS VACCINATED!"
        PRINT @(80,190) "<hit space to continue>"
        DO WHILE INKEY$ <> " "
           PAUSE 5
        LOOP
            
        GameInit
        DrawPlatform(COL_BLUE)
        DrawPlanets
    END IF

    PAUSE 5 ' Small delay to control game speed
LOOP
