import pygame
import sys

Pygame.init()

# Window
WIDTH, HEIGHT = 800, 600
Screen = pygame.display.set_mode((WIDTH, HEIGHT))
Pygame.display.set_caption("Magical Conquest Prototype")

Clock = pygame.time.Clock()

# Colors
WHITE = (255, 255, 255)
RED = (200, 50, 50)
BLUE = (50, 100, 255)
BLACK = (20, 20, 20)

# Player
Player = pygame.Rect(100, 100, 50, 50)
Player_speed = 5
Player_hp = 100

# Enemy
Enemy = pygame.Rect(500, 300, 50, 50)
Enemy_hp = 50

Font = pygame.font.SysFont(None, 30)

Running = True

while running:
    Screen.fill(BLACK)

    # Events
    For event in pygame.event.get():
        If event.type == pygame.QUIT:
            Running = False

    # Movement
    Keys = pygame.key.get_pressed()

    If keys[pygame.K_w]:
        Player.y -= player_speed
    If keys[pygame.K_s]:
        Player.y += player_speed
    If keys[pygame.K_a]:
        Player.x -= player_speed
    If keys[pygame.K_d]:
        Player.x += player_speed

    # Attack
    If keys[pygame.K_SPACE]:
        If player.colliderect(enemy):
            Enemy_hp -= 1

    # Enemy AI
    If enemy.x < player.x:
        Enemy.x += 2
    If enemy.x > player.x:
        Enemy.x -= 2
    If enemy.y < player.y:
        Enemy.y += 2
    If enemy.y > player.y:
        Enemy.y -= 2

    # Enemy damage
    If player.colliderect(enemy):
        Player_hp -= 0.05

    # Draw
    Pygame.draw.rect(screen, BLUE, player)
    Pygame.draw.rect(screen, RED, enemy)

    # HP text
    Hp_text = font.render(f"Player HP: {int(player_hp)}", True, WHITE)
    Enemy_text = font.render(f"Enemy HP: {int(enemy_hp)}", True, WHITE)

    Screen.blit(hp_text, (10, 10))
    Screen.blit(enemy_text, (10, 40))

    # Enemy death
    If enemy_hp <= 0:
        Enemy.x = 1000

    # Player death
    If player_hp <= 0:
        Print("You Died")
        Running = False

    Pygame.display.flip()
    Clock.tick(60)

Pygame.quit()
Sys.exit()
