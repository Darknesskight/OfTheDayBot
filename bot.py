import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import json
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image
import io

# Load environment variables
load_dotenv()

async def category_autocomplete(
    interaction: discord.Interaction, 
    current: str
) -> list[app_commands.Choice[str]]:
    """Global autocomplete function for category parameters"""
    data_dir = Path('data')
    if not data_dir.exists():
        return []
    
    categories = []
    for item in data_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            categories.append(item.name)
    
    # Filter categories based on what user has typed so far
    filtered_categories = [
        cat for cat in categories 
        if current.lower() in cat.lower()
    ]
    # Return up to 25 choices (Discord's limit)
    return [
        app_commands.Choice(name=cat, value=cat)
        for cat in filtered_categories[:25]
    ]

class DailyCog(commands.Cog):
    """Cog for daily posting commands"""
    
    # Create a command group for daily-related commands
    daily_group = app_commands.Group(name="daily", description="Daily posting commands")
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Unified storage for bot configurations
        self.configs = {}
        # Lock for thread-safe config operations
        self._config_lock = asyncio.Lock()
        # Load configurations from file if exists
        self.load_configs()
    
    def load_configs(self):
        """Load bot configurations from file"""
        try:
            if os.path.exists('configs.json'):
                with open('configs.json', 'r') as f:
                    self.configs = json.load(f)
        except Exception as e:
            print(f"Error loading configs: {e}")
    
    async def save_configs(self):
        """Save bot configurations to file (thread-safe)"""
        async with self._config_lock:
            try:
                with open('configs.json', 'w') as f:
                    json.dump(self.configs, f, indent=2)
            except Exception as e:
                print(f"Error saving configs: {e}")
    
    def has_admin_permissions(self, user, guild):
        """Check if user has administrator permissions, server ownership, or bot ownership"""
        if user.guild_permissions.administrator:
            return True
        if user.id == guild.owner_id:
            return True
        try:
            if self.bot.application and self.bot.application.owner and user.id == self.bot.application.owner.id:
                return True
        except AttributeError:
            pass
        return False
    
    def get_categories(self):
        """Get all available categories from data directory"""
        data_dir = Path('data')
        if not data_dir.exists():
            return []
        
        categories = []
        for item in data_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                categories.append(item.name)
        return categories
    
    def get_item_ids_in_category(self, category):
        """Get all item IDs (directory names) in a category - fast O(1) directory read"""
        category_dir = Path(f'data/{category}')
        if not category_dir.exists():
            return []
        return [d.name for d in category_dir.iterdir() if d.is_dir()]
    
    def get_item_by_id(self, category, item_id):
        """Load a single item by its ID - O(1) operation"""
        item_dir = Path(f'data/{category}/{item_id}')
        if not item_dir.exists() or not item_dir.is_dir():
            return None
        
        info_file = item_dir / 'info.json'
        if not info_file.exists():
            return None
        
        try:
            with open(info_file, 'r', encoding='utf-8') as f:
                item_data = json.load(f)
                item_data['id'] = item_id
                item_data['folder_path'] = str(item_dir)
                image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
                for ext in image_extensions:
                    image_file = item_dir / f'image{ext}'
                    if image_file.exists():
                        item_data['image_path'] = str(image_file)
                        break
                return item_data
        except Exception as e:
            print(f"Error loading {info_file}: {e}")
            return None
    
    def get_random_items(self, category, count=1, exclude_ids=None):
        """Get random items without loading all items - optimized for large categories
        
        Args:
            category: The category to pull from
            count: Number of items to select
            exclude_ids: List of item IDs to exclude from selection
        """
        item_ids = self.get_item_ids_in_category(category)
        
        # Filter out excluded items
        if exclude_ids:
            available_ids = [id for id in item_ids if id not in exclude_ids]
        else:
            available_ids = item_ids
        
        if len(available_ids) < count:
            return None
        
        selected_ids = random.sample(available_ids, count)
        items = []
        for item_id in selected_ids:
            item = self.get_item_by_id(category, item_id)
            if item:
                items.append(item)
        
        # Return None if we couldn't load enough valid items
        if len(items) < count:
            return None
        return items
    
    def get_pulled_items(self, guild_id, post_type, category):
        """Get list of already pulled item IDs for a guild/post_type/category"""
        if guild_id not in self.configs:
            return []
        if post_type not in self.configs[guild_id]:
            return []
        if category not in self.configs[guild_id][post_type]:
            return []
        return self.configs[guild_id][post_type][category].get('pulled_items', [])
    
    async def add_pulled_items(self, guild_id, post_type, category, item_ids):
        """Add item IDs to the pulled list"""
        if guild_id not in self.configs:
            return
        if post_type not in self.configs[guild_id]:
            return
        if category not in self.configs[guild_id][post_type]:
            return
        
        config = self.configs[guild_id][post_type][category]
        if 'pulled_items' not in config:
            config['pulled_items'] = []
        
        config['pulled_items'].extend(item_ids)
        await self.save_configs()
    
    async def clear_pulled_items(self, guild_id, post_type, category):
        """Clear the pulled items list for a guild/post_type/category"""
        if guild_id not in self.configs:
            return
        if post_type not in self.configs[guild_id]:
            return
        if category not in self.configs[guild_id][post_type]:
            return
        
        self.configs[guild_id][post_type][category]['pulled_items'] = []
        await self.save_configs()
        print(f"All items pulled for {category} in guild {guild_id} ({post_type}). Resetting pool.")
    
    def get_items_in_category(self, category):
        """Get all items in a specific category (loads all - use sparingly for large categories)"""
        category_dir = Path(f'data/{category}')
        if not category_dir.exists():
            return []
        
        items = []
        for item_dir in category_dir.iterdir():
            if item_dir.is_dir():
                info_file = item_dir / 'info.json'
                if info_file.exists():
                    try:
                        with open(info_file, 'r', encoding='utf-8') as f:
                            item_data = json.load(f)
                            item_data['id'] = item_dir.name
                            item_data['folder_path'] = str(item_dir)
                            image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
                            for ext in image_extensions:
                                image_file = item_dir / f'image{ext}'
                                if image_file.exists():
                                    item_data['image_path'] = str(image_file)
                                    break
                            items.append(item_data)
                    except Exception as e:
                        print(f"Error loading {info_file}: {e}")
        return items
    
    async def create_item_embed(self, item, title_prefix=""):
        """Create an embed for an item with image support"""
        embed = discord.Embed(
            title=f"{title_prefix}{item['name']}",
            description=item['description'],
            color=0x00ff00
        )
        
        if item.get('link'):
            embed.add_field(name="Learn More", value=f"[Click here]({item['link']})", inline=False)
        
        image_path = None
        if item.get('image_path') and os.path.exists(item['image_path']):
            image_path = item['image_path']
        elif os.path.exists('data/default-image.png'):
            image_path = 'data/default-image.png'
        
        if image_path:
            file = discord.File(image_path, filename="image.png")
            embed.set_image(url="attachment://image.png")
            return embed, file
        
        return embed, None
    
    def create_vs_image(self, contestant1, contestant2, category):
        """Create a combined VS image for matchup with fixed height"""
        images = []
        target_height = 400
        
        for path in [contestant1.get('image_path'), contestant2.get('image_path')]:
            try:
                img = Image.open(path)
                img = img.convert('RGBA')
                images.append(img)
            except (FileNotFoundError, IOError, AttributeError):
                default_img = Image.open('data/default-image.png')
                default_img = default_img.convert('RGBA')
                images.append(default_img)
        
        resized_images = []
        for img in images:
            aspect_ratio = img.width / img.height
            new_width = int(target_height * aspect_ratio)
            resized = img.resize((new_width, target_height), Image.Resampling.LANCZOS)
            resized_images.append(resized)
        
        total_width = sum(img.width for img in resized_images)
        final_height = target_height
        
        combined = Image.new('RGBA', (total_width, final_height), (0, 0, 0, 0))
        
        x_offset = 0
        for img in resized_images:
            combined.paste(img, (x_offset, 0), img)
            x_offset += img.width

        return combined
    
    async def close_active_poll(self, guild_id, category):
        """Close the active poll for a specific category in a guild if one exists"""
        if guild_id not in self.configs:
            return False
        
        if 'matchup' not in self.configs[guild_id] or category not in self.configs[guild_id]['matchup']:
            return False
        
        matchup_config = self.configs[guild_id]['matchup'][category]
        if 'active_poll' not in matchup_config:
            return False
        
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return False
            
        poll_message_id = matchup_config['active_poll']
        channel_id = matchup_config['channel_id']
        channel = guild.get_channel(channel_id)
        
        if not channel:
            del self.configs[guild_id]['matchup'][category]['active_poll']
            await self.save_configs()
            return False
        
        try:
            message = await channel.fetch_message(poll_message_id)
            if message and message.poll and not message.poll.is_finalised():
                await message.poll.end()
                print(f"Closed active poll {poll_message_id} for category {category} in guild {guild_id}")
            
            del self.configs[guild_id]['matchup'][category]['active_poll']
            await self.save_configs()
            return True
            
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            del self.configs[guild_id]['matchup'][category]['active_poll']
            await self.save_configs()
            print(f"Removed inaccessible poll from tracking: {e}")
            return False
    
    def should_post_today(self, guild_config):
        """Check if we should post today based on scheduled time and last post time"""
        now = datetime.now()
        scheduled_time_str = guild_config.get('time')
        if not scheduled_time_str:
            return False
            
        try:
            hour, minute = map(int, scheduled_time_str.split(':'))
            scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, AttributeError):
            return False
        
        last_post_str = guild_config.get('last_post')
        if last_post_str:
            try:
                last_post = datetime.fromisoformat(last_post_str)
            except (ValueError, TypeError):
                last_post = None
        else:
            last_post = None
        
        return (now >= scheduled_today and 
                (last_post is None or last_post < scheduled_today))
    
    async def post_daily_item(self, channel, category, guild_id=None):
        """Post a random item from category to channel (no duplicates until all items pulled)"""
        # Get already pulled items to exclude
        pulled_items = self.get_pulled_items(guild_id, 'daily', category) if guild_id else []
        
        # Try to get a random item excluding already pulled ones
        random_items = self.get_random_items(category, 1, exclude_ids=pulled_items)
        
        # If no items available (all have been pulled), celebrate and reset!
        if not random_items and pulled_items:
            total_items = len(self.get_item_ids_in_category(category))
            await channel.send(f"🎉 **Cycle Complete!** We've featured all {total_items} items in {category}! Starting a fresh cycle...")
            await self.clear_pulled_items(guild_id, 'daily', category)
            random_items = self.get_random_items(category, 1)
        
        if not random_items:
            await channel.send(f"No items found in category: {category}")
            return
        
        random_item = random_items[0]
        embed, file = await self.create_item_embed(random_item, f"{category} of the Day: ")
        
        if file:
            await channel.send(embed=embed, file=file)
        else:
            await channel.send(embed=embed)
        
        if guild_id and guild_id in self.configs and 'daily' in self.configs[guild_id] and category in self.configs[guild_id]['daily']:
            self.configs[guild_id]['daily'][category]['last_post'] = datetime.now().isoformat()
            # Track the pulled item
            await self.add_pulled_items(guild_id, 'daily', category, [random_item['id']])
    
    async def post_daily_matchup(self, channel, category, guild_id):
        """Post a daily matchup poll to the channel (no duplicates until all items pulled)"""
        pulled_items = self.get_pulled_items(guild_id, 'matchup', category)
        all_ids = self.get_item_ids_in_category(category)
        available_count = len(all_ids) - len(pulled_items)
        old_cycle_items = []
        
        contestants = self.get_random_items(category, min(available_count, 2), exclude_ids=pulled_items)
        
        if len(contestants or []) < 2:
            # Cycle complete - store what we got, reset, and get the rest
            old_cycle_items = contestants or []
            if len(old_cycle_items) == 1:
                await channel.send(f"🎉 **Cycle Complete!** We've featured {len(all_ids) - 1} items in {category} match-ups! Using the last remaining item alongside a new challenger...")
            else:
                await channel.send(f"🎉 **Cycle Complete!** We've featured all {len(all_ids)} items in {category} match-ups! Starting a fresh cycle...")
            await self.clear_pulled_items(guild_id, 'matchup', category)
            
            needed = 2 - len(old_cycle_items)
            new_items = self.get_random_items(category, needed, exclude_ids=[c['id'] for c in old_cycle_items])
            contestants = old_cycle_items + (new_items or [])
        
        if len(contestants) < 2:
            await channel.send(f"Need at least 2 items in category '{category}' for a daily match-up.")
            return
        
        await self.close_active_poll(guild_id, category)
        
        embed = discord.Embed(
            title=f"🥊 Daily {category} Match-up!",
            description="Who wins in a match-up? Vote in the poll below!",
            color=0xff6600
        )
        
        # Build description with learn more link for contestant 1
        desc1 = contestants[0]['description'][:400] + ("..." if len(contestants[0]['description']) > 400 else "")
        if contestants[0].get('link'):
            desc1 += f"\n\n**Learn More**\n[Click here]({contestants[0]['link']})"
        
        # Build description with learn more link for contestant 2
        desc2 = contestants[1]['description'][:400] + ("..." if len(contestants[1]['description']) > 400 else "")
        if contestants[1].get('link'):
            desc2 += f"\n\n**Learn More**\n[Click here]({contestants[1]['link']})"
        
        embed.add_field(
            name=f"🔴 {contestants[0]['name']}",
            value=desc1,
            inline=True
        )
        
        embed.add_field(
            name=f"🔵 {contestants[1]['name']}",
            value=desc2,
            inline=True
        )
        
        vs_image = self.create_vs_image(contestants[0], contestants[1], category)
        
        vs_bytes = io.BytesIO()
        vs_image.save(vs_bytes, format='PNG')
        vs_bytes.seek(0)
        
        vs_file = discord.File(vs_bytes, filename="vs_matchup.png")
        embed.set_image(url="attachment://vs_matchup.png")
        
        await channel.send(embed=embed, file=vs_file)
        
        poll = discord.Poll(
            question=f"Who wins this {category} match-up?",
            duration=timedelta(hours=24)
        )
        
        poll.add_answer(text=contestants[0]['name'], emoji="🔴")
        poll.add_answer(text=contestants[1]['name'], emoji="🔵")
        
        poll_message = await channel.send(poll=poll)
        
        self.configs[guild_id]['matchup'][category]['active_poll'] = poll_message.id
        self.configs[guild_id]['matchup'][category]['last_post'] = datetime.now().isoformat()
        
        # Track pulled items (excluding old cycle items that shouldn't be in new cycle tracking)
        old_cycle_ids = [c['id'] for c in old_cycle_items]
        items_to_track = [c['id'] for c in contestants if c['id'] not in old_cycle_ids]
        await self.add_pulled_items(guild_id, 'matchup', category, items_to_track)
    
    # Slash Commands - Daily Group
    @daily_group.command(name="categories", description="List all available categories")
    async def daily_categories(self, interaction: discord.Interaction):
        """List all available categories"""
        if not self.has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You need administrator permissions, server ownership, or bot ownership to use this command.", ephemeral=True)
            return
            
        categories = self.get_categories()
        if not categories:
            await interaction.response.send_message("❌ No categories found in data directory.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Available Categories",
            description="\n".join([f"• {cat}" for cat in categories]),
            color=0x0099ff
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @daily_group.command(name="status", description="Show current daily posting configuration for this server")
    async def daily_status(self, interaction: discord.Interaction):
        """Show current daily posting configuration for this server"""
        if not self.has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You need administrator permissions, server ownership, or bot ownership to use this command.", ephemeral=True)
            return
        
        guild_id = str(interaction.guild.id)
        
        if guild_id not in self.configs or (
            'daily' not in self.configs[guild_id] and 
            'matchup' not in self.configs[guild_id]
        ):
            embed = discord.Embed(
                title="📊 Daily Bot Status",
                description="No daily posting configured for this server.\nUse `/daily setup` to get started!",
                color=0x808080
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📊 Daily Bot Status",
            color=0x0099ff
        )
        
        guild_config = self.configs[guild_id]
        
        # Daily Post configurations (multiple categories)
        if 'daily' in guild_config and guild_config['daily']:
            for category, config in guild_config['daily'].items():
                channel = interaction.guild.get_channel(config['channel_id'])
                channel_mention = channel.mention if channel else f"Unknown (ID: {config['channel_id']})"
                items_count = len(self.get_item_ids_in_category(category))
                
                last_post = config.get('last_post', 'Never')
                if last_post != 'Never':
                    try:
                        last_post_dt = datetime.fromisoformat(last_post)
                        last_post = f"<t:{int(last_post_dt.timestamp())}:R>"
                    except (ValueError, TypeError):
                        last_post = 'Unknown'
                
                embed.add_field(
                    name=f"📅 Daily Post: {category}",
                    value=(
                        f"**Items:** {items_count}\n"
                        f"**Channel:** {channel_mention}\n"
                        f"**Time:** {config['time']}\n"
                        f"**Last Post:** {last_post}"
                    ),
                    inline=False
                )
        else:
            embed.add_field(
                name="📅 Daily Posts",
                value="*No daily posts configured*",
                inline=False
            )
        
        # Matchup configurations (multiple categories)
        if 'matchup' in guild_config and guild_config['matchup']:
            for category, config in guild_config['matchup'].items():
                channel = interaction.guild.get_channel(config['channel_id'])
                channel_mention = channel.mention if channel else f"Unknown (ID: {config['channel_id']})"
                items_count = len(self.get_item_ids_in_category(category))
                
                last_post = config.get('last_post', 'Never')
                if last_post != 'Never':
                    try:
                        last_post_dt = datetime.fromisoformat(last_post)
                        last_post = f"<t:{int(last_post_dt.timestamp())}:R>"
                    except (ValueError, TypeError):
                        last_post = 'Unknown'
                
                active_poll = "Yes" if 'active_poll' in config else "No"
                
                embed.add_field(
                    name=f"🥊 Match-up Poll: {category}",
                    value=(
                        f"**Items:** {items_count}\n"
                        f"**Channel:** {channel_mention}\n"
                        f"**Time:** {config['time']}\n"
                        f"**Last Post:** {last_post}\n"
                        f"**Active Poll:** {active_poll}"
                    ),
                    inline=False
                )
        else:
            embed.add_field(
                name="🥊 Match-up Polls",
                value="*No match-up polls configured*",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @daily_group.command(name="setup", description="Set up daily posting for a category")
    @app_commands.describe(
        post_type="Type of post to configure",
        category="Category to post from",
        channel="Text channel to post items to",
        time_hour="Hour (0-23) to post at",
        time_minute="Minute (0-59) to post at"
    )
    @app_commands.choices(post_type=[
        app_commands.Choice(name="Daily Post", value="daily"),
        app_commands.Choice(name="Match-up Poll", value="matchup")
    ])
    @app_commands.autocomplete(category=category_autocomplete)
    async def daily_setup(
        self,
        interaction: discord.Interaction,
        post_type: app_commands.Choice[str],
        category: str,
        channel: discord.TextChannel,
        time_hour: int,
        time_minute: int = 0
    ):
        """Set up daily posting for a category"""
        if not self.has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You need administrator permissions, server ownership, or bot ownership to use this command.", ephemeral=True)
            return
        
        if category not in self.get_categories():
            await interaction.response.send_message(f"❌ Category '{category}' not found.", ephemeral=True)
            return
        
        if not (0 <= time_hour <= 23) or not (0 <= time_minute <= 59):
            await interaction.response.send_message("❌ Invalid time. Hour must be 0-23, minute must be 0-59.", ephemeral=True)
            return
        
        bot_permissions = channel.permissions_for(interaction.guild.me)
        if not bot_permissions.send_messages or not bot_permissions.embed_links:
            await interaction.response.send_message(f"❌ I don't have permission to send messages or embed links in {channel.mention}. Please check my permissions.", ephemeral=True)
            return
        
        guild_id = str(interaction.guild.id)
        current_timestamp = datetime.now().isoformat()
        
        if guild_id not in self.configs:
            self.configs[guild_id] = {}
        
        if post_type.value not in self.configs[guild_id]:
            self.configs[guild_id][post_type.value] = {}
        
        self.configs[guild_id][post_type.value][category] = {
            'channel_id': channel.id,
            'time': f"{time_hour:02d}:{time_minute:02d}",
            'last_post': current_timestamp
        }
        await self.save_configs()
        
        embed = discord.Embed(
            title=f"✅ {post_type.name} Configured",
            description=f"**Category:** {category}\n**Channel:** {channel.mention}\n**Time:** {time_hour:02d}:{time_minute:02d}",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @daily_group.command(name="remove", description="Remove daily posting configuration for a category")
    @app_commands.describe(
        post_type="Type of post to remove",
        category="Category to remove configuration for"
    )
    @app_commands.choices(post_type=[
        app_commands.Choice(name="Daily Post", value="daily"),
        app_commands.Choice(name="Match-up Poll", value="matchup")
    ])
    @app_commands.autocomplete(category=category_autocomplete)
    async def daily_remove(self, interaction: discord.Interaction, post_type: app_commands.Choice[str], category: str):
        """Remove daily posting configuration for a category"""
        if not self.has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You need administrator permissions, server ownership, or bot ownership to use this command.", ephemeral=True)
            return
        
        guild_id = str(interaction.guild.id)
        if guild_id not in self.configs or post_type.value not in self.configs[guild_id] or category not in self.configs[guild_id][post_type.value]:
            await interaction.response.send_message(f"❌ No {post_type.name.lower()} configuration found for category '{category}'.", ephemeral=True)
            return
        
        del self.configs[guild_id][post_type.value][category]
        
        # Clean up empty structures
        if not self.configs[guild_id][post_type.value]:
            del self.configs[guild_id][post_type.value]
        if not self.configs[guild_id]:
            del self.configs[guild_id]
        await self.save_configs()
        
        embed = discord.Embed(
            title=f"✅ {post_type.name} Removed",
            description=f"**Category:** {category}\n{post_type.name} has been disabled for this category.",
            color=0xff9900
        )
        await interaction.response.send_message(embed=embed)
    
    @daily_group.command(name="endpoll", description="Manually close the active poll for a category")
    @app_commands.describe(category="Category of the poll to close")
    @app_commands.autocomplete(category=category_autocomplete)
    async def daily_endpoll(self, interaction: discord.Interaction, category: str):
        """Manually close the active poll for a category"""
        if not self.has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You need administrator permissions, server ownership, or bot ownership to use this command.", ephemeral=True)
            return
        
        if category not in self.get_categories():
            await interaction.response.send_message(f"❌ Category '{category}' not found.", ephemeral=True)
            return
        
        guild_id = str(interaction.guild.id)
        
        # Check if there's an active poll for this category
        if (guild_id not in self.configs or 
            'matchup' not in self.configs[guild_id] or 
            category not in self.configs[guild_id]['matchup'] or
            'active_poll' not in self.configs[guild_id]['matchup'][category]):
            await interaction.response.send_message(f"❌ No active poll found for category '{category}'.", ephemeral=True)
            return
        
        success = await self.close_active_poll(guild_id, category)
        
        if success:
            embed = discord.Embed(
                title="✅ Poll Closed",
                description=f"Successfully ended the active {category} poll.",
                color=0x00ff00
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="⚠️ Poll Cleanup",
                description=f"The active poll reference for {category} has been cleaned up (poll may have already ended or been deleted).",
                color=0xff9900
            )
            await interaction.response.send_message(embed=embed)
    
    @daily_group.command(name="reroll", description="Manually trigger a daily post or matchup (for testing)")
    @app_commands.describe(
        post_type="Type of post to generate",
        category="Category to select items from"
    )
    @app_commands.choices(post_type=[
        app_commands.Choice(name="Daily Post", value="daily"),
        app_commands.Choice(name="Match-up Poll", value="matchup")
    ])
    @app_commands.autocomplete(category=category_autocomplete)
    async def reroll(
        self,
        interaction: discord.Interaction,
        post_type: app_commands.Choice[str],
        category: str
    ):
        """Manually trigger a daily post or matchup (for testing)"""
        if not self.has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ You need administrator permissions, server ownership, or bot ownership to use this command.", ephemeral=True)
            return
        
        if category not in self.get_categories():
            await interaction.response.send_message(f"❌ Category '{category}' not found.", ephemeral=True)
            return
        
        guild_id = str(interaction.guild.id)
        
        # Check if this category is configured for the given post type
        if (guild_id not in self.configs or 
            post_type.value not in self.configs[guild_id] or
            category not in self.configs[guild_id][post_type.value]):
            await interaction.response.send_message(f"❌ {post_type.name} not configured for category '{category}'. Use `/daily setup` first.", ephemeral=True)
            return
        
        channel_id = self.configs[guild_id][post_type.value][category]['channel_id']
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("❌ Configured channel not found.", ephemeral=True)
            return
        
        # Use fast counting for validation
        item_count = len(self.get_item_ids_in_category(category))
        if item_count == 0:
            await interaction.response.send_message(f"❌ No items found in category '{category}'.", ephemeral=True)
            return
        
        if post_type.value == 'matchup' and item_count < 2:
            await interaction.response.send_message(f"❌ Need at least 2 items in category '{category}' for a match-up.", ephemeral=True)
            return
        
        await interaction.response.send_message(f"🎲 Generating {post_type.name.lower()} for {category}...", ephemeral=True)
        
        if post_type.value == 'daily':
            await self.post_daily_item(channel, category, str(interaction.guild_id))
        else:
            await self.post_daily_matchup(channel, category, str(interaction.guild_id))
        
        await interaction.followup.send(f"✅ {post_type.name} sent to {channel.mention}!", ephemeral=True)
    
    @tasks.loop(minutes=1)
    async def daily_post_task(self):
        """Background task for daily posts and matchups"""
        for guild_id, guild_configs in self.configs.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            
            # Process all daily post categories
            if 'daily' in guild_configs:
                for category, config in guild_configs['daily'].items():
                    if self.should_post_today(config):
                        channel = guild.get_channel(config['channel_id'])
                        if channel:
                            await self.post_daily_item(channel, category, guild_id)
            
            # Process all matchup categories
            if 'matchup' in guild_configs:
                for category, config in guild_configs['matchup'].items():
                    if self.should_post_today(config):
                        channel = guild.get_channel(config['channel_id'])
                        if channel:
                            await self.post_daily_matchup(channel, category, guild_id)
    
    @daily_post_task.before_loop
    async def before_daily_task(self):
        """Wait for bot to be ready before starting the daily task"""
        await self.bot.wait_until_ready()
    
    async def cog_load(self):
        """Called when the cog is loaded - start the daily task"""
        self.daily_post_task.start()
    
    async def cog_unload(self):
        """Called when the cog is unloaded - stop the daily task"""
        self.daily_post_task.cancel()

class OfTheDayBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Use empty command prefix since we only use slash commands
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
    
    async def setup_hook(self):
        """Called when the bot is starting up - add cogs and sync commands"""
        # Add the cog
        await self.add_cog(DailyCog(self))
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        print(f'Bot is in {len(self.guilds)} guilds')

# Create bot instance
bot = OfTheDayBot()

if __name__ == "__main__":
    bot.run(os.getenv('BOT_TOKEN'))
