import asyncio
from card_generator import CardGenerator
import os
from rich.console import Console
from rich.progress import Progress
import traceback

console = Console()

async def main():
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            console.print("[red]Please set your OPENAI_API_KEY environment variable[/red]")
            return
            
        generator = CardGenerator(api_key)
        
        console.print("[bold green]Welcome to the Card Game Generator![/bold green]")
        console.print("\nPlease describe your game concept:")
        game_concept = input("> ")  # Single input point
        
        console.print("\n[bold cyan]Starting generation process...[/bold cyan]")
        with Progress() as progress:
            # Generate rules
            task1 = progress.add_task("[cyan]Generating game rules...", total=1)
            rules_text, card_types = await generator.generate_game_rules(game_concept)
            progress.update(task1, advance=1)
            
            # Save rules to PDF
            generator.create_rules_pdf(rules_text, 'rules.pdf')
            console.print("\n[green]✓[/green] Rules generated and saved to 'rules.pdf'")
            
            # Get total cards from rules
            total_cards = sum(card_type['quantity'] for card_type in card_types)
            console.print(f"\n[cyan]Generating {total_cards} cards...[/cyan]")
            
            # Generate cards and backgrounds
            task2 = progress.add_task("[cyan]Generating cards and backgrounds...", total=total_cards * 2)
            
            cards_data = []
            for card_type in card_types:
                console.print(f"\n[yellow]Generating {card_type['type']} cards ({card_type['quantity']})[/yellow]")
                for i in range(card_type['quantity']):
                    success = False
                    while not success:
                        try:
                            console.print(f"[cyan]→ Card {i+1}/{card_type['quantity']}[/cyan]")
                            card = await generator.generate_cards_content(game_concept, 1, card_type)
                            cards_data.extend(card)
                            progress.update(task2, advance=1)
                            
                            console.print(f"[cyan]→ Background {i+1}[/cyan]")
                            cards_data[-1]['background'] = await generator.generate_card_background(cards_data[-1]['image_prompt'])
                            progress.update(task2, advance=1)
                            
                            console.print(f"[green]✓[/green] Card {i+1} complete")
                            success = True
                        except Exception as e:
                            console.print(f"[red]Failed to generate card {i+1}. Retrying...[/red]")
                            if len(cards_data) > 0 and 'background' not in cards_data[-1]:
                                cards_data.pop()  # Remove incomplete card
                            await asyncio.sleep(1)
            
            console.print("\n[cyan]Creating final PDF...[/cyan]")
            generator.create_card_pdf(cards_data, 'cards.pdf')
            console.print("\n[green bold]✓ Generation complete![/green bold]")
            console.print("Files created: rules.pdf, cards.pdf")

    except Exception as e:
        console.print(f"\n[red bold]ERROR:[/red bold] {str(e)}")
        console.print("[red]Traceback:[/red]")
        console.print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main()) 